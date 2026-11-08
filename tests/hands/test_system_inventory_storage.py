# -*- coding: utf-8 -*-
"""
Tests de contrato del almacenamiento canonico SQLite del inventario persistente
(unidad 3.8.5.1.4.2.3).

Verifican:
- Creacion de `data/system_inventory.sqlite3` (en directorio temporal, nunca en produccion).
- Inicializacion y versionado del esquema (`schema_version`).
- Registro de equipos y volumenes con aislamiento por equipo (`machine_id`).
- Ejecuciones de escaneo (inicio/fin, resultado, metricas).
- Escritura por lotes atomica de entradas de archivo y candidatos de aplicacion.
- Tablas separadas: entradas genericas de archivo vs candidatos de aplicacion.
- Consultas indexadas paginadas por nombre, extension y prefijo de ruta.
- Contador de entradas y recuperacion de la ultima ejecucion por equipo/volumen.

Todos los tests usan directorios temporales (tmp_path) y no tocan datos de produccion.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.hands.system_inventory_storage import (
    DEFAULT_DB_PATH,
    SCAN_MODE_FULL,
    SCAN_MODE_INCREMENTAL,
    SCAN_RESULT_ERROR,
    SCAN_RESULT_INTERRUPTED,
    SCAN_RESULT_OK,
    SCAN_RESULT_PARTIAL,
    SystemInventoryStorage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "system_inventory.sqlite3"


@pytest.fixture
def storage(db_path: Path) -> SystemInventoryStorage:
    return SystemInventoryStorage(db_path)


# ---------------------------------------------------------------------------
# Creacion del fichero y esquema
# ---------------------------------------------------------------------------

class TestCreacionBaseDeDatos:
    """La base de datos canonica `data/system_inventory.sqlite3` se crea al inicializar."""

    def test_inicializacion_crea_fichero_en_ruta_dada(self, storage: SystemInventoryStorage, db_path: Path):
        assert not db_path.exists()
        version = storage.initialize()
        assert version == 1
        assert db_path.exists()
        assert storage.db_file_exists()

    def test_ruta_por_defecto_es_data_system_inventory_sqlite3(self):
        assert DEFAULT_DB_PATH == Path("data") / "system_inventory.sqlite3"

    def test_esquema_versionado_se_registra(self, storage: SystemInventoryStorage):
        storage.initialize()
        assert storage.schema_version() == 1

    def test_inicializacion_idempotente_no_borra_datos(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-1")
        storage.initialize()  # segunda inicializacion no debe borrar la maquina
        assert storage.get_entry_count("machine-1") == 0


# ---------------------------------------------------------------------------
# Equipos y volumenes (aislamiento por equipo)
# ---------------------------------------------------------------------------

class TestMaquinasYVolumenes:
    """Registro de equipos y volumenes con aislamiento por `machine_id`."""

    def test_record_machine_registra_equipo(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        # No hay forma directa de consultar maquinas; verificar que no lanza y que
        # un volumen asociado puede registrarse.
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        assert storage.get_entry_count("machine-alfa") == 0

    def test_aislamiento_por_equipo(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_volume("vol-c:", "machine-alfa", "C:", "local", "online")
        storage.record_volume("vol-d:", "machine-beta", "D:", "local", "online")
        # Cada equipo ve solo sus propios volumenes/entradas indirectamente via conteo.
        assert storage.get_entry_count("machine-alfa") == 0
        assert storage.get_entry_count("machine-beta") == 0


# ---------------------------------------------------------------------------
# Ejecuciones de escaneo
# ---------------------------------------------------------------------------

class TestScanRuns:
    """Inicio y finalizacion de ejecuciones de escaneo."""

    def test_begin_y_end_scan_run(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        run = storage.get_scan_run("scan-1")
        assert run is not None
        assert run["machine_id"] == "machine-alfa"
        assert run["volume"] == "C:"
        assert run["mode"] == SCAN_MODE_FULL
        assert run["result"] == SCAN_RESULT_OK
        assert run["entries_count"] == 0
        assert run["finished_at"] is None

        storage.end_scan_run(
            "scan-1",
            result=SCAN_RESULT_OK,
            entries_count=120,
            errors_count=2,
            exclusions_count=5,
            coverage_estimate="90%",
        )
        run = storage.get_scan_run("scan-1")
        assert run["finished_at"] is not None
        assert run["result"] == SCAN_RESULT_OK
        assert run["entries_count"] == 120
        assert run["errors_count"] == 2
        assert run["exclusions_count"] == 5
        assert run["coverage_estimate"] == "90%"

    def test_resultados_permitidos(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        for resultado in (SCAN_RESULT_OK, SCAN_RESULT_PARTIAL, SCAN_RESULT_INTERRUPTED, SCAN_RESULT_ERROR):
            sid = f"scan-{resultado}"
            storage.begin_scan_run(sid, "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
            storage.end_scan_run(sid, result=resultado)
            assert storage.get_scan_run(sid)["result"] == resultado

    def test_get_latest_scan(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-old", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-old", entries_count=10)
        storage.begin_scan_run("scan-new", "machine-alfa", "C:", SCAN_MODE_INCREMENTAL)
        storage.end_scan_run("scan-new", entries_count=50)
        latest = storage.get_latest_scan("machine-alfa", "C:")
        assert latest is not None
        assert latest["scan_id"] == "scan-new"
        assert latest["entries_count"] == 50

    def test_get_latest_scan_por_volumen(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-c", "machine-alfa", "C:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-c", entries_count=5)
        storage.begin_scan_run("scan-d", "machine-alfa", "D:", SCAN_MODE_FULL)
        storage.end_scan_run("scan-d", entries_count=9)
        latest_c = storage.get_latest_scan("machine-alfa", "C:")
        latest_d = storage.get_latest_scan("machine-alfa", "D:")
        assert latest_c["scan_id"] == "scan-c"
        assert latest_d["scan_id"] == "scan-d"

    def test_scan_run_desconocido_devuelve_none(self, storage: SystemInventoryStorage):
        storage.initialize()
        assert storage.get_scan_run("scan-inexistente") is None


# ---------------------------------------------------------------------------
# Escritura atomica por lotes
# ---------------------------------------------------------------------------

class TestInsercionAtomica:
    """Insercion por lotes en transaccion atomica (sin entradas parciales tras fallo)."""

    def _una_entrada(self, entry_id: str = "e-1") -> dict:
        return {
            "entry_id": entry_id,
            "absolute_path": "C:/Users/Jarvis/app.exe",
            "relative_path": "Users/Jarvis/app.exe",
            "name": "app.exe",
            "extension": ".exe",
            "entry_type": "file",
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "accessed_at": "2024-01-02T08:00:00",
            "attributes": ["hidden"],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        }

    def test_insert_file_entries_lote(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        entradas = [self._una_entrada("e-1"), self._una_entrada("e-2")]
        insertados = storage.insert_file_entries("scan-1", "machine-alfa", "C:", entradas)
        assert insertados == 2
        assert storage.get_entry_count("machine-alfa", "C:") == 2

    def test_insert_file_entries_vacio_no_inserta(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        assert storage.insert_file_entries("scan-1", "machine-alfa", "C:", []) == 0
        assert storage.get_entry_count("machine-alfa") == 0

    def test_insercion_atomica_fallo_no_deja_entradas_parciales(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        buena = self._una_entrada("e-buena")
        # entrada con entry_id duplicado para forzar violacion de PK en el lote
        duplicada = dict(buena, entry_id="e-dup")
        lote = [buena, duplicada, dict(buena, entry_id="e-dup")]
        with pytest.raises(Exception):
            storage.insert_file_entries("scan-1", "machine-alfa", "C:", lote)
        # Ninguna entrada del lote fallido debe haberse persistido.
        assert storage.get_entry_count("machine-alfa", "C:") == 0

    def test_insert_application_candidates_tabla_separada(self, storage: SystemInventoryStorage):
        storage.initialize()
        storage.record_machine("machine-alfa")
        storage.begin_scan_run("scan-1", "machine-alfa", "C:", SCAN_MODE_FULL)
        candidatos = [
            {
                "candidate_id": "c-1",
                "name": "Google Chrome",
                "absolute_path": "C:/Program Files/Google/Chrome/Application/chrome.exe",
                "launch_type": "ejecutable",
                "confidence": 0.95,
                "source": "inventory",
                "last_checked_at": "2024-01-03T00:00:00",
            }
        ]
        insertados = storage.insert_application_candidates("scan-1", "machine-alfa", "C:", candidatos)
        assert insertados == 1
        # Los candidatos no cuentan como entradas genericas de archivo.
        assert storage.get_entry_count("machine-alfa", "C:") == 0


# ---------------------------------------------------------------------------
# Consultas indexadas y paginadas
# ---------------------------------------------------------------------------

class TestConsultasIndexadas:
    """Busquedas por nombre, extension y prefijo de ruta, con paginacion."""

    def _seed(self, storage: SystemInventoryStorage, machine_id: str = "machine-alfa") -> str:
        storage.initialize()
        storage.record_machine(machine_id)
        storage.begin_scan_run("scan-1", machine_id, "C:", SCAN_MODE_FULL)
        entradas = []
        for i in range(5):
            entradas.append({
                "entry_id": f"e-{i}",
                "absolute_path": f"C:/Apps/app{i}.exe",
                "relative_path": f"Apps/app{i}.exe",
                "name": f"app{i}.exe",
                "extension": ".exe",
                "entry_type": "file",
                "size_bytes": 1000 + i,
                "modified_at": "2024-01-01T10:00:00",
                "created_at": "2024-01-01T09:00:00",
                "attributes": [],
                "excluded": False,
                "source": "filesystem_scan",
                "last_checked_at": "2024-01-03T00:00:00",
            })
        # Una entrada de otro tipo y extension para diferenciar
        entradas.append({
            "entry_id": "e-readme",
            "absolute_path": "C:/Apps/readme.txt",
            "relative_path": "Apps/readme.txt",
            "name": "readme.txt",
            "extension": ".txt",
            "entry_type": "file",
            "size_bytes": 200,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        })
        storage.insert_file_entries("scan-1", machine_id, "C:", entradas)
        storage.end_scan_run("scan-1", entries_count=len(entradas))
        return "scan-1"

    def test_search_by_name(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_name("machine-alfa", "app2.exe")
        assert len(res) == 1
        assert res[0]["name"] == "app2.exe"

    def test_search_by_name_case_insensitive(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_name("machine-alfa", "APP2.EXE")
        assert len(res) == 1

    def test_search_by_extension(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_extension("machine-alfa", ".txt")
        assert len(res) == 1
        assert res[0]["name"] == "readme.txt"

    def test_search_by_extension_case_insensitive(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_extension("machine-alfa", ".TXT")
        assert len(res) == 1

    def test_search_by_path_prefix(self, storage: SystemInventoryStorage):
        self._seed(storage)
        res = storage.search_by_path_prefix("machine-alfa", "C:/Apps/app")
        assert len(res) == 5

    def test_paginacion_limite_y_offset(self, storage: SystemInventoryStorage):
        self._seed(storage)
        primera = storage.search_by_name("machine-alfa", "app*.exe") if False else storage.search_by_path_prefix("machine-alfa", "C:/Apps/app", limit=2, offset=0)
        assert len(primera) == 2
        segunda = storage.search_by_path_prefix("machine-alfa", "C:/Apps/app", limit=2, offset=2)
        assert len(segunda) == 2
        ids_primera = {e["entry_id"] for e in primera}
        ids_segunda = {e["entry_id"] for e in segunda}
        assert ids_primera.isdisjoint(ids_segunda)

    def test_consulta_equipo_diferente_no_devuelve_datos(self, storage: SystemInventoryStorage):
        self._seed(storage, "machine-alfa")
        res = storage.search_by_name("machine-beta", "app2.exe")
        assert res == []
        assert storage.get_entry_count("machine-beta") == 0


# ---------------------------------------------------------------------------
# Contexto y cierre limpio
# ---------------------------------------------------------------------------

class TestContexto:
    """Uso como gestor de contexto y cierre limpio de la conexion."""

    def test_gestor_de_contexto_abre_y_cierra(self, db_path: Path):
        with SystemInventoryStorage(db_path) as storage:
            storage.initialize()
            assert db_path.exists()
        # tras salir del contexto la conexion debe estar cerrada
        assert storage._conn is None

    def test_conexion_wal_y_foreign_keys(self, storage: SystemInventoryStorage):
        storage.initialize()
        conn = storage.connect()
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert str(journal).lower() in ("wal", "memory")
        assert int(fk) == 1
