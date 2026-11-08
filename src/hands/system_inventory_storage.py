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
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


SCHEMA_VERSION = 2

# Detectar si el sistema de archivos es sensible a mayusculas y minusculas.
# Windows y macOS (por defecto) son insensibles; Linux y la mayoria de Unix son sensibles.
_FILESYSTEM_CASE_SENSITIVE = os.path.normcase("A") != os.path.normcase("a")


def normalize_path(path: str) -> str:
    """Normaliza una ruta para uso como clave unica, respetando la case-sensitividad del SO.

    En sistemas insensibles a mayusculas (Windows, macOS por defecto) la ruta se
    normaliza a minusculas para que "C:/App.EXE" y "c:/app.exe" se consideren la
    misma entrada. En sistemas sensibles (Linux) se conserva tal cual, ya que son
    archivos distintos.
    """
    p = path.replace("\\", "/")
    if not _FILESYSTEM_CASE_SENSITIVE:
        p = p.lower()
    return p


DEFAULT_DB_PATH = Path("data") / "system_inventory.sqlite3"

# Ruta canonica del manifiesto/resumen JSON ligero del inventario (3.8.5.1.4.2.10).
# Se guarda junto a la base de datos SQLite y resume version, equipo, volumenes
# y ultimo escaneo sin almacenar el listado entero de archivos.
DEFAULT_MANIFEST_PATH = Path("data") / "system_inventory_manifest.json"

# Valores admitidos para el modo de escaneo (3.8.5.1.4.2.6).
SCAN_MODE_FULL = "completo"
SCAN_MODE_INCREMENTAL = "incremental"

# Valores admitidos para el resultado de una ejecucion de escaneo.
SCAN_RESULT_OK = "ok"
SCAN_RESULT_PARTIAL = "parcial"
SCAN_RESULT_INTERRUPTED = "interrumpido"
SCAN_RESULT_ERROR = "error"


class ConcurrentScanError(Exception):
    """Se levanta cuando se intenta iniciar un escaneo mientras otro esta en curso
    para el mismo equipo y volumen, para impedir que dos escaneos simultaneos
    corrompan o dupliquen el inventario."""


# Registro de bloqueos de escaneo en proceso, claveado por (machine_id, volume).
# Permite serializar el inicio de escaneos dentro del mismo proceso para evitar
# que dos escaneos concurrentes escriban sobre el mismo inventario (3.8.5.1.4.2.9).
_SCAN_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_SCAN_LOCKS_GUARD: threading.Lock = threading.Lock()

# ------------------------------------------------------------------ #
# Migraciones de esquema verificables (3.8.5.1.4.2.8).
#
# Cada migracion es un paso discreto, versionado y comprobable:
# (version_origen, version_destino, nombre, funcion). Las funciones
# reciben la conexion SQLite y se ejecutan dentro de una transaccion;
# si alguna falla, se hace rollback y la version del esquema no avanza,
# de modo que un inventario de version previa nunca se borra ni se
# reinterpreta silenciosamente.
# ------------------------------------------------------------------ #

def _migracion_v1_a_v2(conn: sqlite3.Connection) -> None:
    """Migracion v1 -> v2: agrega la columna `normalized_path` a `file_entries`.

    Es una operacion aditiva: conserva todas las filas existentes y les
    asigna el valor por defecto (cadena vacia) en la nueva columna. No
    elimina, ni reinterpreta, datos de inventarios de version anterior.
    """
    try:
        conn.execute(
            "ALTER TABLE file_entries ADD COLUMN normalized_path TEXT NOT NULL DEFAULT ''"
        )
    except sqlite3.OperationalError:
        # La columna ya existe (base creada ya en esquema v2): nada que migrar.
        pass


# (version_origen, version_destino, nombre, funcion_de_migracion)
_MIGRACIONES: list[tuple[int, int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, 2, "agregar normalized_path a file_entries", _migracion_v1_a_v2),
]


def _conteos_tablas(conn: sqlite3.Connection) -> dict[str, int | None]:
    """Devuelve el conteo de filas de cada tabla del esquema (integridad de datos)."""
    tablas = (
        "schema_version",
        "machines",
        "volumes",
        "scan_runs",
        "file_entries",
        "application_candidates",
    )
    conteos: dict[str, int | None] = {}
    for tabla in tablas:
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM {tabla}")
            conteos[tabla] = int(cur.fetchone()[0])
        except sqlite3.OperationalError:
            conteos[tabla] = None
    return conteos


def _aplicar_migraciones(
    conn: sqlite3.Connection, version_origen: int, version_destino: int
) -> None:
    """Aplica las migraciones pendientes de `version_origen` a `version_destino`.

    Las migraciones se aplican en orden, una a una, cada una dentro de su
    propia transaccion y con la version del esquema actualizada al terminar.
    Antes y despues se comparan los conteos de filas de todas las tablas: si
    una migracion pierde o agrega datos silenciosamente, se cancela y se
    levanta un error (no se borra ni se reinterpreta el inventario previo).
    """
    version = version_origen
    conteos_antes = _conteos_tablas(conn)
    while version < version_destino:
        siguiente: tuple[int, str, Callable[[sqlite3.Connection], None]] | None = None
        for origen, destino, nombre, fn in _MIGRACIONES:
            if origen == version:
                siguiente = (destino, nombre, fn)
                break
        if siguiente is None:
            raise RuntimeError(
                f"No hay migracion registrada de esquema v{version} a v{version + 1}."
            )
        destino, nombre, fn = siguiente
        try:
            conn.execute("BEGIN")
            fn(conn)
        except Exception:
            conn.rollback()
            raise
        version = destino
        conn.execute("UPDATE schema_version SET version = ?", (version,))
        conn.commit()
    conteos_despues = _conteos_tablas(conn)
    if conteos_antes != conteos_despues:
        raise RuntimeError(
            f"La migracion de esquema v{version_origen} a v{version_destino} "
            f"altero el volumen de datos: antes={conteos_antes}, despues={conteos_despues}"
        )

_SCHEMA_TABLES_SQL = f"""
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
    normalized_path TEXT NOT NULL DEFAULT '',
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
"""

_SCHEMA_INDEXES_SQL = """
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

-- Clave unica por equipo/volumen/ruta normalizada (3.8.5.1.4.2.5).
-- Impide duplicar la misma entrada de archivo para un equipo y volumen dados.
CREATE UNIQUE INDEX IF NOT EXISTS idx_file_entries_unique_path
    ON file_entries(machine_id, volume, normalized_path);

-- Indice de consulta por ruta normalizada (soporta busquedas case-correctas).
CREATE INDEX IF NOT EXISTS idx_file_entries_normalized_path
    ON file_entries(machine_id, normalized_path);

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
        # Manifiesto JSON ligero junto a la base de datos (3.8.5.1.4.2.10).
        self.manifest_path = self.db_path.parent / "system_inventory_manifest.json"

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
        """Crea las tablas e indices si no existen, aplica migraciones pendientes
        y devuelve la version del esquema.

        Flujo (3.8.5.1.4.2.8):
        1. Crea tablas (IF NOT EXISTS) con el esquema actual (v2). En bases nuevas
           `file_entries` ya trae `normalized_path`; en bases v1 existentes no.
        2. Detecta la version actual almacenada (0 si es una base nueva).
        3. Si la base viene de una version anterior (0 < version < v2), aplica las
           migraciones registradas en orden: cada una dentro de su propia
           transaccion, actualizando la version del esquema al terminar. Una
           base con version superior a la conocida no se degrada ni se le
           reinterpreta el contenido.
        4. Crea todos los indices (incluido el unico por ruta normalizada), que
           requieren que las migraciones ya hayan ejecutado.
        5. Registra/actualiza la version del esquema sin borrar datos previos.
        """
        conn = self.connect()
        # 1. Crear tablas (schema_version incluido) con el esquema actual.
        conn.executescript(_SCHEMA_TABLES_SQL)

        # 2. Detectar version actual (0 si la tabla schema_version esta vacia o nueva).
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        current_version = int(row["version"]) if row else 0

        # 3. Aplicar migraciones pendientes, si las hay.
        if row is None or current_version == 0:
            # Base nueva (o sin version inicializada): las tablas ya se crearon con
            # el esquema actual; registrar/actualizar la version.
            if row is None:
                conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        elif 0 < current_version < SCHEMA_VERSION:
            _aplicar_migraciones(conn, current_version, SCHEMA_VERSION)
        elif current_version > SCHEMA_VERSION:
            # Esquema mas nuevo del que este codigo entiende: no se baja la version
            # ni se tocan los datos del inventario previo (3.8.5.1.4.2.8).
            return current_version

        # 4. Crear indices (despues de las migraciones, que pueden agregar columnas).
        conn.executescript(_SCHEMA_INDEXES_SQL)

        # 5. Registrar/actualizar version sin borrar datos.
        conn.commit()
        return SCHEMA_VERSION

    def schema_version(self) -> int:
        """Devuelve la version actual del esquema almacenada en disco."""
        conn = self.connect()
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        return int(row["version"]) if row else 0

    # ------------------------------------------------------------------ #
    # Control de concurrencia de escaneos (3.8.5.1.4.2.9).
    # ------------------------------------------------------------------ #

    @classmethod
    def _acquire_scan_lock(cls, machine_id: str, volume: str) -> None:
        """Adquiere el bloqueo de escaneo para (machine_id, volumen) de forma no bloqueante.

        Si otro escaneo ya esta en curso para la misma clave, levanta
        `ConcurrentScanError` para impedir ejecuciones simultaneas que pudieran
        corromper o duplicar el inventario.
        """
        key = (machine_id, volume)
        with _SCAN_LOCKS_GUARD:
            lock = _SCAN_LOCKS.get(key)
            if lock is None:
                lock = threading.Lock()
                _SCAN_LOCKS[key] = lock
        if not lock.acquire(blocking=False):
            raise ConcurrentScanError(
                f"Ya hay un escaneo en curso para machine_id={machine_id!r}, "
                f"volume={volume!r}. No se permiten dos escaneos simultaneos "
                "sobre el mismo inventario."
            )

    @classmethod
    def _release_scan_lock(cls, machine_id: str, volume: str) -> None:
        """Libera el bloqueo de escaneo para (machine_id, volumen) y lo quita del
        registro cuando ya no esta retenido, para que la clave quede disponible
        para futuros escaneos."""
        key = (machine_id, volume)
        with _SCAN_LOCKS_GUARD:
            lock = _SCAN_LOCKS.pop(key, None)
        if lock is not None:
            lock.release()

    @classmethod
    def has_active_scan(cls, machine_id: str, volume: str) -> bool:
        """Devuelve True si hay un escaneo en curso para (machine_id, volumen)."""
        key = (machine_id, volume)
        with _SCAN_LOCKS_GUARD:
            lock = _SCAN_LOCKS.get(key)
        if lock is None:
            return False
        return lock.locked()

    def verify_journal_mode(self) -> str:
        """Devuelve el modo de journaling activo y comprueba que sea adecuado para
        escrituras concurrentes (WAL permite lecturas concurrentes y escrituras
        serializadas sin bloqueos prolongados).

        Retorna el modo actual (p. ej. "wal"). El llamante puede verificar que
        el valor sea "wal" antes de iniciar escaneos (3.8.5.1.4.2.9).
        """
        conn = self.connect()
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        return str(journal)

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
        # Mantener el manifiesto coherente con el estado de volumenes en SQLite (3.8.5.1.4.2.10).
        self.write_manifest(machine_id)

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
        """Registra el inicio de una ejecucion de escaneo.

        Valida que `mode` sea SCAN_MODE_FULL o SCAN_MODE_INCREMENTAL
        (contrato de unidad 3.8.5.1.4.2.6: modalidad completo/incremental
        guardada en cada ejecucion de escaneo).

        Adquiere el bloqueo de concurrencia para (machine_id, volumen) antes de
        iniciar: si otro escaneo esta en curso para la misma clave, levanta
        `ConcurrentScanError` (3.8.5.1.4.2.9). El bloqueo se libera en
        `end_scan_run` (o ante cualquier fallo aqui).

        El nuevo escaneo se registra con resultado SCAN_RESULT_INTERRUPTED
        (estado no confirmado): solo end_scan_run con SCAN_RESULT_OK lo
        confirma como completo (3.8.5.1.4.2.7). Cualquier scan_run previo del
        mismo equipo y volumen que quede sin finalizar se marca como
        interrumpido para no presentar media base de datos como inventario
        completo.
        """
        if mode not in (SCAN_MODE_FULL, SCAN_MODE_INCREMENTAL):
            raise ValueError(
                f"Modo de escaneo no valido: {mode!r}. "
                "Use SCAN_MODE_FULL ('completo') o SCAN_MODE_INCREMENTAL ('incremental')."
            )
        if started_at is None:
            started_at = _now_iso()
        # Adquirir bloqueo de concurrencia antes de tocar el inventario.
        # Se libera en end_scan_run (o ante cualquier fallo aqui).
        self._acquire_scan_lock(machine_id, volume)
        try:
            conn = self.connect()
            self.record_machine(machine_id, created_at=started_at)
            ahora = _now_iso()
            # BEGIN IMMEDIATE adquiere el bloqueo de escritura de SQLite de
            # inmediato, serializando escrituras y evitando que dos escaneos
            # concurrentes corrompan la base (3.8.5.1.4.2.9).
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Un scan_run iniciado pero nunca finalizado (escaneo
                # interrumpido de una ejecucion previa) no debe presentarse
                # como inventario completo (3.8.5.1.4.2.7): se marca como
                # interrumpido antes de iniciar el nuevo.
                conn.execute(
                    """
                    UPDATE scan_runs
                    SET finished_at = ?, result = ?
                    WHERE machine_id = ? AND volume = ? AND finished_at IS NULL
                    """,
                    (ahora, SCAN_RESULT_INTERRUPTED, machine_id, volume),
                )
                conn.execute(
                    """
                    INSERT INTO scan_runs(scan_id, machine_id, volume, mode, started_at,
                                          finished_at, result, entries_count, errors_count,
                                          exclusions_count, coverage_estimate)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, 0, 0, 0, NULL)
                    """,
                    (scan_id, machine_id, volume, mode, started_at, SCAN_RESULT_INTERRUPTED),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        except Exception:
            self._release_scan_lock(machine_id, volume)
            raise

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
        """Finaliza una ejecucion de escaneo con su resultado y metricas.

        Valida que `result` sea uno de los valores permitidos
        (contrato de unidad 3.8.5.1.4.2.6: resultado guardado en cada
        ejecucion de escaneo). Solo SCAN_RESULT_OK representa un escaneo
        completo; el estado inicial registrado por begin_scan_run es
        SCAN_RESULT_INTERRUPTED (3.8.5.1.4.2.7).

        Libera el bloqueo de concurrencia de (machine_id, volumen) asociado a
        este escaneo al terminar, incluso si la finalizacion falla
        (3.8.5.1.4.2.9).
        """
        if finished_at is None:
            finished_at = _now_iso()
        conn = self.connect()
        # Recuperar machine_id y volumen para liberar el bloqueo al terminar,
        # incluso si la validacion de resultado falla o el escaneo no existe.
        row = conn.execute(
            "SELECT machine_id, volume FROM scan_runs WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        if result not in (
            SCAN_RESULT_OK,
            SCAN_RESULT_PARTIAL,
            SCAN_RESULT_INTERRUPTED,
            SCAN_RESULT_ERROR,
        ):
            if row is not None:
                self._release_scan_lock(row["machine_id"], row["volume"])
            raise ValueError(
                f"Resultado de escaneo no valido: {result!r}. "
                "Use SCAN_RESULT_OK, SCAN_RESULT_PARTIAL, SCAN_RESULT_INTERRUPTED o SCAN_RESULT_ERROR."
            )
        # BEGIN IMMEDIATE serializa la escritura al finalizar el escaneo.
        conn.execute("BEGIN IMMEDIATE")
        try:
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
            # Mantener el manifiesto coherente con el ultimo escaneo en SQLite (3.8.5.1.4.2.10).
            self.write_manifest(row["machine_id"])
        except Exception:
            conn.rollback()
            raise
        finally:
            if row is not None:
                self._release_scan_lock(row["machine_id"], row["volume"])

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

        Cada entrada se indexa por la clave unica (machine_id, volume,
        normalized_path); intentar insertar la misma ruta dos veces para un
        mismo equipo/volumen viola la restriccion de unicidad y revierte el lote.
        """
        if not entries:
            return 0
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                """
                INSERT INTO file_entries(
                    entry_id, scan_id, machine_id, volume, absolute_path,
                    normalized_path, relative_path, name, extension, entry_type,
                    size_bytes, modified_at, created_at, accessed_at, attributes,
                    excluded, source, last_checked_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    (
                        e.get("entry_id"),
                        scan_id,
                        machine_id,
                        volume,
                        e.get("absolute_path"),
                        normalize_path(e.get("absolute_path", "")),
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
            conn.execute("BEGIN IMMEDIATE")
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

    def search_by_state(
        self,
        machine_id: str,
        excluded: bool,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Busca entradas por estado de exclusicion (disponible vs excluida).

        Usa el indice `idx_file_entries_excluded(machine_id, excluded)` para
        consultas eficientes por estado (3.8.5.1.4.2.5).
        """
        conn = self.connect()
        cur = conn.execute(
            "SELECT * FROM file_entries WHERE machine_id = ? AND excluded = ? "
            "ORDER BY absolute_path LIMIT ? OFFSET ?",
            (machine_id, 1 if excluded else 0, limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]

    def db_file_exists(self) -> bool:
        """Devuelve True si el fichero de la base de datos existe en disco."""
        return self.db_path.exists()

    # ------------------------------------------------------------------ #
    # Manifiesto JSON ligero del inventario (3.8.5.1.4.2.10).
    # ------------------------------------------------------------------ #
    def write_manifest(self, machine_id: str) -> dict:
        """Escribe/actualiza el manifiesto JSON ligero de resumen del inventario.

        El manifiesto contiene la version del esquema, el identificador del
        equipo, los volumenes descubiertos y la informacion de la ultima
        ejecucion de escaneo. No almacena el listado entero de archivos
        (eso reside en SQLite). Se mantiene coherente con la base de datos
        SQLite: cada llamada lee el estado actual de las tablas y lo refleja
        en el fichero JSON.

        Retorna el diccionario del manifiesto escrito.
        """
        conn = self.connect()

        # Version del esquema almacenada en SQLite.
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        version = int(row["version"]) if row is not None else 0

        # Volumenes descubiertos para este equipo.
        cur = conn.execute(
            """
            SELECT volume_id, volume, volume_type, state, first_seen_at, last_seen_at
            FROM volumes WHERE machine_id = ? ORDER BY volume
            """,
            (machine_id,),
        )
        volumes = [dict(r) for r in cur.fetchall()]

        # Ultima ejecucion de escaneo de este equipo.
        cur = conn.execute(
            """
            SELECT scan_id, volume, mode, started_at, finished_at, result,
                   entries_count, errors_count, exclusions_count, coverage_estimate
            FROM scan_runs WHERE machine_id = ? ORDER BY started_at DESC LIMIT 1
            """,
            (machine_id,),
        )
        scan_row = cur.fetchone()
        last_scan = dict(scan_row) if scan_row is not None else None

        manifest = {
            "version": version,
            "machine_id": machine_id,
            "volumes": volumes,
            "last_scan": last_scan,
            "updated_at": _now_iso(),
        }

        # Escribir el fichero JSON (crear directorio padre si no existe).
        manifest_path = self.manifest_path
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

        return manifest

    def read_manifest(self) -> Optional[dict]:
        """Lee el manifiesto JSON ligero si existe, o None si no hay ninguno."""
        if not self.manifest_path.exists():
            return None
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)


def _now_iso() -> str:
    """Devuelve la fecha y hora actual en ISO 8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat()
