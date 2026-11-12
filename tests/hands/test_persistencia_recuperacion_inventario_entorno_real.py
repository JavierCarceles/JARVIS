# -*- coding: utf-8 -*-
"""
Verificacion real de persistencia en disco, recuperacion desde nueva instancia,
migracion de esquema y base corrupta/ausente (unidad 3.8.5.1.4.10.2).

Cada prueba opera sobre ficheros SQLite REALES en un directorio temporal
(tmp_path). No hay mocks que decidan el resultado: se comprueba el estado del
fichero de base de datos antes y despues de cada operacion, abriendo una
NUEVA instancia de SystemInventoryStorage para simular un reinicio de JARVIS.

Esto cubre los cuatro aspectos de la unidad:
  1. Persistencia real en disco (los datos sobreviven al cierre de la instancia).
  2. Recuperacion desde una nueva instancia (otro objeto SystemInventoryStorage
     sobre el mismo fichero lee los mismos datos).
  3. Migracion de esquema (una base v1 se lleva a SCHEMA_VERSION).
  4. Base corrupta y base ausente (deteccion, recuperacion desde backup y
     creacion de cero).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.hands.system_inventory_storage import (
    DEFAULT_BACKUP_SUFFIX,
    SCAN_MODE_FULL,
    SCAN_RESULT_OK,
    SCHEMA_VERSION,
    SystemInventoryStorage,
    InventoryBackupError,
    InventoryCorruptError,
    generate_machine_id,
)

MAQUINA = "maquina-verificacion-real"
VOLUMEN_ID = "vol-c"
VOLUMEN = "C:"
SCAN_ID = "scan-verificacion"


def _escribir_inventario_ejemplo(storage: SystemInventoryStorage) -> None:
    """Escribe un conjunto representativo de datos en la base y lo cierra."""
    storage.initialize(machine_id_actual=MAQUINA)
    storage.record_machine(MAQUINA)
    storage.record_volume(VOLUMEN_ID, MAQUINA, VOLUMEN, "local", "online")
    storage.begin_scan_run(SCAN_ID, MAQUINA, VOLUMEN, SCAN_MODE_FULL)
    storage.insert_file_entries(SCAN_ID, MAQUINA, VOLUMEN, [
        {
            "entry_id": "e-1",
            "absolute_path": "C:/Apps/JARVIS/app.exe",
            "relative_path": "Apps/JARVIS/app.exe",
            "name": "app.exe",
            "extension": ".exe",
            "entry_type": "file",
            "size_bytes": 1024,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "accessed_at": "2024-01-02T08:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        },
        {
            "entry_id": "e-2",
            "absolute_path": "C:/Windows/System32/kernel32.dll",
            "relative_path": "Windows/System32/kernel32.dll",
            "name": "kernel32.dll",
            "extension": ".dll",
            "entry_type": "file",
            "size_bytes": 8192,
            "modified_at": "2024-01-01T10:00:00",
            "created_at": "2024-01-01T09:00:00",
            "accessed_at": "2024-01-02T08:00:00",
            "attributes": [],
            "excluded": False,
            "source": "filesystem_scan",
            "last_checked_at": "2024-01-03T00:00:00",
        },
    ])
    storage.end_scan_run(SCAN_ID, result=SCAN_RESULT_OK, entries_count=2)
    storage.close()


def _conteo_tabla(ruta_db: Path, tabla: str) -> int:
    conn = sqlite3.connect(str(ruta_db))
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
    finally:
        conn.close()


def _version_esquema(ruta_db: Path) -> int:
    conn = sqlite3.connect(str(ruta_db))
    try:
        fila = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return int(fila[0]) if fila else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Persistencia real en disco y recuperacion desde nueva instancia
# ---------------------------------------------------------------------------

class TestPersistenciaDiscoYNuevaInstancia:
    """Los datos escritos por una instancia deben leerse por una NUEVA instancia
    sobre el mismo fichero, simulando que JARVIS se cerro y volvio a abrir."""

    def test_datos_sobreviven_al_cierre_y_se_leen_desde_nueva_instancia(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "system_inventory.sqlite3"

        # Primera instancia: escribe y cierra (simula ejecucion previa de JARVIS).
        primera = SystemInventoryStorage(db_path)
        _escribir_inventario_ejemplo(primera)

        # Antes de abrir la nueva instancia, el fichero debe existir en disco
        # y contener los datos escritos.
        assert db_path.exists()
        assert _conteo_tabla(db_path, "machines") == 1
        assert _conteo_tabla(db_path, "volumes") == 1
        assert _conteo_tabla(db_path, "file_entries") == 2
        assert _version_esquema(db_path) == SCHEMA_VERSION

        # Nueva instancia sobre el mismo fichero (simula reinicio de JARVIS).
        segunda = SystemInventoryStorage(db_path)
        version = segunda.initialize(machine_id_actual=MAQUINA)
        assert version == SCHEMA_VERSION
        assert segunda.schema_version() == SCHEMA_VERSION

        # Los datos persisten: misma maquina, volumen y entradas.
        assert _conteo_tabla(db_path, "machines") == 1
        assert _conteo_tabla(db_path, "volumes") == 1
        assert _conteo_tabla(db_path, "scan_runs") == 1
        assert _conteo_tabla(db_path, "file_entries") == 2
        segunda.close()

    def test_nueva_instancia_no_duplica_maquina_ni_volumen(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "system_inventory.sqlite3"
        primera = SystemInventoryStorage(db_path)
        _escribir_inventario_ejemplo(primera)

        segunda = SystemInventoryStorage(db_path)
        segunda.initialize(machine_id_actual=MAQUINA)
        # No debe crear una segunda fila de maquina ni de volumen.
        assert _conteo_tabla(db_path, "machines") == 1
        assert _conteo_tabla(db_path, "volumes") == 1
        segunda.close()


# ---------------------------------------------------------------------------
# 2. Base ausente: inicializar de cero crea el fichero y el esquema actual
# ---------------------------------------------------------------------------

class TestBaseAusente:
    """Si no existe base de datos en disco, initialize() la crea con el esquema
    actual sin requerir una copia de seguridad previa."""

    def test_inicializar_base_ausente_crea_fichero_y_esquema_actual(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "system_inventory.sqlite3"
        assert not db_path.exists()

        storage = SystemInventoryStorage(db_path)
        version = storage.initialize(machine_id_actual=MAQUINA)

        assert version == SCHEMA_VERSION
        assert db_path.exists()
        assert storage.schema_version() == SCHEMA_VERSION
        assert _conteo_tabla(db_path, "machines") == 0
        assert _conteo_tabla(db_path, "file_entries") == 0
        storage.close()


# ---------------------------------------------------------------------------
# 3. Base corrupta: deteccion y recuperacion desde copia de seguridad
# ---------------------------------------------------------------------------

class TestBaseCorrupta:
    """Una base corrupta no se inicializa sobre ella: verify_integrity devuelve
    ok=False y, si existe una copia de seguridad valida, restaurar_desde_backup
    recupera los datos sobre una nueva instancia."""

    def test_base_corrupta_se_detecta_y_se_recupera_desde_backup(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "system_inventory.sqlite3"

        # Primera instancia: escribe datos y crea copia de seguridad.
        primera = SystemInventoryStorage(db_path)
        _escribir_inventario_ejemplo(primera)
        backup = primera.create_backup()
        assert backup.exists()
        assert _version_esquema(backup) == SCHEMA_VERSION

        # Corromper el fichero real de la base (escritura directa sobre disco).
        primera.close()
        db_path.write_bytes(b"esto no es una base de datos SQLite valida")

        # Nueva instancia: verify_integrity debe detectar la corrupcion.
        segunda = SystemInventoryStorage(db_path)
        integridad = segunda.verify_integrity()
        assert integridad["ok"] is False
        assert integridad["error"] is not None

        # Restaurar desde la copia de seguridad valida.
        segunda.restaurar_desde_backup()
        assert segunda.verify_integrity()["ok"] is True

        # Los datos se recuperan: una nueva instancia sobre el fichero restaurado
        # lee los mismos registros.
        segunda.close()
        tercera = SystemInventoryStorage(db_path)
        tercera.initialize(machine_id_actual=MAQUINA)
        assert _conteo_tabla(db_path, "machines") == 1
        assert _conteo_tabla(db_path, "file_entries") == 2
        assert _version_esquema(db_path) == SCHEMA_VERSION
        tercera.close()

    def test_base_corrupta_sin_backup_levanta_InventoryCorruptError(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "system_inventory.sqlite3"
        primera = SystemInventoryStorage(db_path)
        _escribir_inventario_ejemplo(primera)
        primera.close()

        # Corromper sin haber creado copia de seguridad.
        db_path.write_bytes(b"contenido corrupto que invalida la base de datos")

        # Una nueva instancia sobre la base corrupta sin backup debe fallar en
        # alto sin destruir datos recuperables (no hay backup que restaurar).
        storage_corrupto = SystemInventoryStorage(db_path)
        with pytest.raises(InventoryCorruptError):
            storage_corrupto.initialize(machine_id_actual=MAQUINA)

    def test_create_backup_sin_base_levanta_InventoryBackupError(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "system_inventory.sqlite3"
        assert not db_path.exists()
        storage = SystemInventoryStorage(db_path)
        with pytest.raises(InventoryBackupError):
            storage.create_backup()


# ---------------------------------------------------------------------------
# 4. Migracion de esquema: base v1 antigua se lleva a SCHEMA_VERSION
# ---------------------------------------------------------------------------

class TestMigracionEsquema:
    """Una base creada con un esquema previo (v1) se migra aplicando todas las
    migraciones registradas en orden, sin perder datos, hasta SCHEMA_VERSION."""

    def _crear_db_v1(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO schema_version(version) VALUES (1)")
            conn.execute(
                """
                CREATE TABLE machines (
                    machine_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE volumes (
                    volume_id TEXT PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    volume_type TEXT,
                    state TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE scan_runs (
                    scan_id TEXT PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    result TEXT NOT NULL,
                    entries_count INTEGER NOT NULL DEFAULT 0,
                    errors_count INTEGER NOT NULL DEFAULT 0,
                    exclusions_count INTEGER NOT NULL DEFAULT 0,
                    coverage_estimate TEXT,
                    FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE file_entries (
                    entry_id TEXT PRIMARY KEY,
                    scan_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    extension TEXT NOT NULL DEFAULT '',
                    entry_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    modified_at TEXT,
                    created_at TEXT,
                    accessed_at TEXT,
                    attributes TEXT NOT NULL DEFAULT '[]',
                    excluded INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'filesystem_scan',
                    last_checked_at TEXT NOT NULL,
                    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id),
                    FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE application_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    scan_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    name TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    launch_type TEXT,
                    confidence REAL,
                    source TEXT NOT NULL DEFAULT 'inventory',
                    last_checked_at TEXT NOT NULL,
                    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id),
                    FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
                )
                """
            )
            conn.execute(
                "INSERT INTO machines(machine_id, created_at) VALUES (?, ?)",
                (MAQUINA, "2024-01-01T00:00:00"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_base_v1_se_migra_a_esquema_actual_sin_perder_datos(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "system_inventory.sqlite3"
        self._crear_db_v1(db_path)
        assert _version_esquema(db_path) == 1

        storage = SystemInventoryStorage(db_path)
        version = storage.initialize(machine_id_actual=MAQUINA)

        assert version == SCHEMA_VERSION
        assert storage.schema_version() == SCHEMA_VERSION
        assert _version_esquema(db_path) == SCHEMA_VERSION

        # La migracion v3->v4 reemplazo el indice unico; debe existir el nuevo.
        conn = sqlite3.connect(str(db_path))
        try:
            indices = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "idx_file_entries_unique_path_scan" in indices
        # La columna normalized_path (v1->v2) debe existir en file_entries.
        conn = sqlite3.connect(str(db_path))
        try:
            columnas = {
                row[1]
                for row in conn.execute("PRAGMA table_info(file_entries)").fetchall()
            }
        finally:
            conn.close()
        assert "normalized_path" in columnas

        # Los datos previos a la migracion se conservan.
        assert _conteo_tabla(db_path, "machines") == 1
        storage.close()
