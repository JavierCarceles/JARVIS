"""
Almacenamiento canonico SQLite del indice de inventario del sistema de archivos.

Unidad 3.8.5.1.4.2.3: crea `data/system_inventory.sqlite3` como almacenamiento
canonico del indice de inventario persistente (3.8.5.1.4.2) y documenta su
formato en `docs/README_DATA.md`.

Este modulo implementa el gestor de almacenamiento SQLite para el indice de
inventario. No implementa el recorrido de directorios (3.8.5.1.4.4) ni la
clasificacion de aplicaciones (3.8.5.1.4.7); solo provee el almacenamiento
consultable, transaccional y versionado del indice.

Provee:
- Inicializacion y creacion de esquema versionado (tabla `schema_version`).
- Tablas: `machines`, `volumes`, `scan_runs`, `file_entries`,
  `application_candidates`.
- Escritura por lotes en transaccion atomica (un escaneo interrumpido no deja
  media base presentada como inventario completo).
- Consultas indexadas por nombre normalizado, extension, tipo, ruta, volumen
  y estado.
- Aislamiento por equipo (machine_id): un inventario pertenece al equipo que
  lo creo (3.8.5.1.4.1.3).

Todo el esquema usa SQLite de la biblioteca estandar (`sqlite3`), ya presente
en el proyecto (p. ej. `src/utils/advanced_logger.py`).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = 1

DEFAULT_DB_PATH = Path("data") / "system_inventory.sqlite3"

# Valores admitidos para el modo de escaneo (3.8.5.1.4.2.6).
SCAN_MODE_FULL = "completo"
SCAN_MODE_INCREMENTAL = "incremental"

# Valores admitidos para el resultado de una ejecucion de escaneo.
SCAN_RESULT_OK = "ok"
SCAN_RESULT_PARTIAL = "parcial"
SCAN_RESULT_INTERRUPTED = "interrumpido"
SCAN_RESULT_ERROR = "error"

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS machines (
    machine_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS volumes (
    volume_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    volume TEXT NOT NULL,
    volume_type TEXT,
    state TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
);

CREATE TABLE IF NOT EXISTS scan_runs (
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
);

CREATE TABLE IF NOT EXISTS file_entries (
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
);

CREATE TABLE IF NOT EXISTS application_candidates (
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
);

CREATE INDEX IF NOT EXISTS idx_file_entries_machine_volume
    ON file_entries(machine_id, volume);
CREATE INDEX IF NOT EXISTS idx_file_entries_name
    ON file_entries(machine_id, lower(name));
CREATE INDEX IF NOT EXISTS idx_file_entries_extension
    ON file_entries(machine_id, lower(extension));
CREATE INDEX IF NOT EXISTS idx_file_entries_entry_type
    ON file_entries(machine_id, entry_type);
CREATE INDEX IF NOT EXISTS idx_file_entries_absolute_path
    ON file_entries(machine_id, absolute_path);
CREATE INDEX IF NOT EXISTS idx_file_entries_excluded
    ON file_entries(machine_id, excluded);

CREATE INDEX IF NOT EXISTS idx_app_candidates_machine_volume
    ON application_candidates(machine_id, volume);
CREATE INDEX IF NOT EXISTS idx_app_candidates_name
    ON application_candidates(machine_id, lower(name));
CREATE INDEX IF NOT EXISTS idx_app_candidates_launch_type
    ON application_candidates(machine_id, launch_type);

CREATE INDEX IF NOT EXISTS idx_scan_runs_machine_volume
    ON scan_runs(machine_id, volume);
CREATE INDEX IF NOT EXISTS idx_scan_runs_started_at
    ON scan_runs(machine_id, started_at);
"""


class SystemInventoryStorage:
    """Gestor del almacenamiento canonico SQLite del inventario de archivos."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        # El directorio padre debe existir antes de crear la base de datos.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------ #
    # Conexion
    # ------------------------------------------------------------------ #
    def connect(self) -> sqlite3.Connection:
        """Abre (o reutiliza) la conexion SQLite con WAL e integridad."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            # WAL permite lecturas concurrentes y escrituras secuenciales
            # seguras; evita bloqueos prolongados en escaneos largos.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        """Cierra la conexion si esta abierta."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SystemInventoryStorage":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Esquema
    # ------------------------------------------------------------------ #
    def initialize(self) -> int:
        """Crea las tablas e indices si no existen y devuelve la version del esquema."""
        conn = self.connect()
        conn.executescript(_SCHEMA_SQL)
        # Registrar/actualizar la version del esquema sin borrar datos previos.
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            if int(row["version"]) != SCHEMA_VERSION:
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        conn.commit()
        return SCHEMA_VERSION

    def schema_version(self) -> int:
        """Devuelve la version actual del esquema almacenada en disco."""
        conn = self.connect()
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        return int(row["version"]) if row else 0

    # ------------------------------------------------------------------ #
    # Entidades maestras
    # ------------------------------------------------------------------ #
    def record_machine(self, machine_id: str, created_at: Optional[str] = None) -> None:
        """Registra el equipo local si aun no existe (aislamiento por equipo)."""
        if created_at is None:
            created_at = _now_iso()
        conn = self.connect()
        conn.execute(
            "INSERT OR IGNORE INTO machines(machine_id, created_at) VALUES (?, ?)",
            (machine_id, created_at),
        )
        conn.commit()

    def record_volume(
        self,
        volume_id: str,
        machine_id: str,
        volume: str,
        volume_type: Optional[str] = None,
        state: Optional[str] = None,
        first_seen_at: Optional[str] = None,
        last_seen_at: Optional[str] = None,
    ) -> None:
        """Registra o actualiza un volumen descubierto para un equipo."""
        now = _now_iso()
        if first_seen_at is None:
            first_seen_at = now
        if last_seen_at is None:
            last_seen_at = now
        conn = self.connect()
        self.record_machine(machine_id, created_at=first_seen_at)
        conn.execute(
            """
            INSERT INTO volumes(volume_id, machine_id, volume, volume_type, state,
                                first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(volume_id) DO UPDATE SET
                volume = excluded.volume,
                volume_type = excluded.volume_type,
                state = excluded.state,
                last_seen_at = excluded.last_seen_at
            """,
            (volume_id, machine_id, volume, volume_type, state, first_seen_at, last_seen_at),
        )
        conn.commit()

    # ------------------------------------------------------------------ #
    # Ejecuciones de escaneo
    # ------------------------------------------------------------------ #
    def begin_scan_run(
        self,
        scan_id: str,
        machine_id: str,
        volume: str,
        mode: str,
        started_at: Optional[str] = None,
    ) -> None:
        """Registra el inicio de una ejecucion de escaneo."""
        if started_at is None:
            started_at = _now_iso()
        conn = self.connect()
        self.record_machine(machine_id, created_at=started_at)
        conn.execute(
            """
            INSERT INTO scan_runs(scan_id, machine_id, volume, mode, started_at,
                                  finished_at, result, entries_count, errors_count,
                                  exclusions_count, coverage_estimate)
            VALUES (?, ?, ?, ?, ?, NULL, ?, 0, 0, 0, NULL)
            """,
            (scan_id, machine_id, volume, mode, started_at, SCAN_RESULT_OK),
        )
        conn.commit()

    def end_scan_run(
        self,
        scan_id: str,
        finished_at: Optional[str] = None,
        result: str = SCAN_RESULT_OK,
        entries_count: int = 0,
        errors_count: int = 0,
        exclusions_count: int = 0,
        coverage_estimate: Optional[str] = None,
    ) -> None:
        """Finaliza una ejecucion de escaneo con su resultado y metricas."""
        if finished_at is None:
            finished_at = _now_iso()
        conn = self.connect()
        conn.execute(
            """
            UPDATE scan_runs
            SET finished_at = ?, result = ?, entries_count = ?, errors_count = ?,
                exclusions_count = ?, coverage_estimate = ?
            WHERE scan_id = ?
            """,
            (finished_at, result, entries_count, errors_count, exclusions_count,
             coverage_estimate, scan_id),
        )
        conn.commit()

    def get_scan_run(self, scan_id: str) -> Optional[dict]:
        """Devuelve los datos de una ejecucion de escaneo o None si no existe."""
        conn = self.connect()
        cur = conn.execute("SELECT * FROM scan_runs WHERE scan_id = ?", (scan_id,))
        row = cur.fetchone()
        return dict(row) if row is not None else None

    def get_latest_scan(self, machine_id: str, volume: Optional[str] = None) -> Optional[dict]:
        """Devuelve la ultima ejecucion de escaneo de un equipo (y opcionalmente volumen)."""
        conn = self.connect()
        if volume is None:
            cur = conn.execute(
                "SELECT * FROM scan_runs WHERE machine_id = ? ORDER BY started_at DESC LIMIT 1",
                (machine_id,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM scan_runs WHERE machine_id = ? AND volume = ? "
                "ORDER BY started_at DESC LIMIT 1",
                (machine_id, volume),
            )
        row = cur.fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------ #
    # Entradas de archivo (escritura por lote atomica)
    # ------------------------------------------------------------------ #
    def insert_file_entries(
        self,
        scan_id: str,
        machine_id: str,
        volume: str,
        entries: list[dict],
    ) -> int:
        """Inserta una lista de entradas de archivo en una transaccion atomica.

        Devuelve el numero de entradas insertadas. Si la transaccion falla, no
        se persiste entrada alguna de este lote.
        """
        if not entries:
            return 0
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            conn.executemany(
                """
                INSERT INTO file_entries(
                    entry_id, scan_id, machine_id, volume, absolute_path,
                    relative_path, name, extension, entry_type, size_bytes,
                    modified_at, created_at, accessed_at, attributes,
                    excluded, source, last_checked_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    (
                        e.get("entry_id"),
                        scan_id,
                        machine_id,
                        volume,
                        e.get("absolute_path"),
                        e.get("relative_path"),
                        e.get("name"),
                        e.get("extension", ""),
                        e.get("entry_type"),
                        int(e.get("size_bytes", 0)),
                        e.get("modified_at"),
                        e.get("created_at"),
                        e.get("accessed_at"),
                        json.dumps(e.get("attributes", []), ensure_ascii=False),
                        1 if e.get("excluded") else 0,
                        e.get("source", "filesystem_scan"),
                        e.get("last_checked_at"),
                    )
                    for e in entries
                ],
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return len(entries)

    # ------------------------------------------------------------------ #
    # Candidatos de aplicación (separados de los registros genericos de archivo)
    # ------------------------------------------------------------------ #
    def insert_application_candidates(
        self,
        scan_id: str,
        machine_id: str,
        volume: str,
        candidates: list[dict],
    ) -> int:
        """Inserta candidatos de aplicación en una transaccion atomica.

        Los candidatos de aplicacion se almacenan en su propia tabla,
        separados de los registros genericos de archivos (3.8.5.1.4.2.4).
        """
        if not candidates:
            return 0
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            conn.executemany(
                """
                INSERT INTO application_candidates(
                    candidate_id, scan_id, machine_id, volume, name,
                    absolute_path, launch_type, confidence, source, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.get("candidate_id"),
                        scan_id,
                        machine_id,
                        volume,
                        c.get("name"),
                        c.get("absolute_path"),
                        c.get("launch_type"),
                        c.get("confidence"),
                        c.get("source", "inventory"),
                        c.get("last_checked_at"),
                    )
                    for c in candidates
                ],
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return len(candidates)

    # ------------------------------------------------------------------ #
    # Consultas indexadas
    # ------------------------------------------------------------------ #
    def search_by_name(
        self,
        machine_id: str,
        name: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Busca entradas de archivo por nombre normalizado (paginado)."""
        conn = self.connect()
        cur = conn.execute(
            "SELECT * FROM file_entries WHERE machine_id = ? AND lower(name) = lower(?) "
            "ORDER BY absolute_path LIMIT ? OFFSET ?",
            (machine_id, name, limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]

    def search_by_extension(
        self,
        machine_id: str,
        extension: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Busca entradas de archivo por extension (paginado)."""
        conn = self.connect()
        cur = conn.execute(
            "SELECT * FROM file_entries WHERE machine_id = ? AND lower(extension) = lower(?) "
            "ORDER BY absolute_path LIMIT ? OFFSET ?",
            (machine_id, extension, limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]

    def search_by_path_prefix(
        self,
        machine_id: str,
        path_prefix: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Busca entradas de archivo por prefijo de ruta absoluta (paginado)."""
        conn = self.connect()
        cur = conn.execute(
            "SELECT * FROM file_entries WHERE machine_id = ? AND absolute_path LIKE ? "
            "ORDER BY absolute_path LIMIT ? OFFSET ?",
            (machine_id, path_prefix + "%", limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_entry_count(self, machine_id: str, volume: Optional[str] = None) -> int:
        """Devuelve el numero total de entradas de archivo de un equipo (y opcionalmente volumen)."""
        conn = self.connect()
        if volume is None:
            cur = conn.execute(
                "SELECT COUNT(*) AS c FROM file_entries WHERE machine_id = ?", (machine_id,)
            )
        else:
            cur = conn.execute(
                "SELECT COUNT(*) AS c FROM file_entries WHERE machine_id = ? AND volume = ?",
                (machine_id, volume),
            )
        return int(cur.fetchone()["c"])

    def db_file_exists(self) -> bool:
        """Devuelve True si el fichero de la base de datos existe en disco."""
        return self.db_path.exists()


def _now_iso() -> str:
    """Devuelve la fecha y hora actual en ISO 8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat()
