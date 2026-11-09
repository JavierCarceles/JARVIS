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
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional


SCHEMA_VERSION = 4

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

# Sufijo del fichero de copia de seguridad junto a la base de datos.
DEFAULT_BACKUP_SUFFIX = ".bak"


class InventoryCorruptError(Exception):
    """La base de datos SQLite del inventario esta corrupta o ilegible y no
    puede usarse como fuente de verdad sin recuperarla desde una copia de
    seguridad valida."""


class InventoryBackupError(Exception):
    """Fallo al crear una copia de seguridad del inventario o al restaurarla.
    Nunca se usa para ocultar un fallo: cuando la copia de seguridad no es
    valida, la base actual queda intacta y no se sobrescribe."""

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


def _migracion_v2_a_v3(conn: sqlite3.Connection) -> None:
    """Migracion v2 -> v3: crea la tabla `lineas_base` para conservar la
    primera instantanea completa (linea base) por volumen.

    Es una operacion aditiva: no elimina ni reinterpreta tablas ni datos
    existentes. Cada equipo y volumen solo puede tener una linea base, la
    primera, preservada como referencia para la deteccion de cambios
    incrementales (unidad 3.8.5.1.4.5.1).
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lineas_base (
            linea_id TEXT PRIMARY KEY,
            machine_id TEXT NOT NULL,
            volume TEXT NOT NULL,
            fecha_base TEXT NOT NULL,
            estado_volumen TEXT NOT NULL,
            cobertura REAL NOT NULL,
            entradas_count INTEGER NOT NULL DEFAULT 0,
            errores_count INTEGER NOT NULL DEFAULT 0,
            scan_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
        )
        """
    )


def _migracion_v3_a_v4(conn: sqlite3.Connection) -> None:
    """Migracion v3 -> v4: adapta la clave unica de `file_entries` para
    soportar escaneos incrementales.

    La clave unica anterior `(machine_id, volume, normalized_path)` impedía
    que la misma ruta existiera en dos escaneos distintos (p. ej. linea base
    y escaneo incremental). Para la deteccion de cambios incrementales
    (3.8.5.1.4.5.2) es necesario que las entradas de diferentes scans
    coexistan con la misma ruta normalizada, diferenciadas por `scan_id`.

    Operacion:
    1. Elimina el indice unico viejo `idx_file_entries_unique_path`.
    2. Crea un nuevo indice unico `idx_file_entries_unique_path_scan` sobre
       (machine_id, volume, normalized_path, scan_id), permitiendo que la
       misma ruta aparezca en varios escaneos sin duplicarse dentro de uno
       mismo.
    """
    conn.execute("DROP INDEX IF EXISTS idx_file_entries_unique_path")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_file_entries_unique_path_scan
            ON file_entries(machine_id, volume, normalized_path, scan_id)
        """
    )


# (version_origen, version_destino, nombre, funcion_de_migracion)
_MIGRACIONES: list[tuple[int, int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, 2, "agregar normalized_path a file_entries", _migracion_v1_a_v2),
    (2, 3, "crear tabla lineas_base", _migracion_v2_a_v3),
    (3, 4, "clave unica de file_entries incluye scan_id", _migracion_v3_a_v4),
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

CREATE TABLE IF NOT EXISTS lineas_base (
    linea_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    volume TEXT NOT NULL,
    fecha_base TEXT NOT NULL,
    estado_volumen TEXT NOT NULL,
    cobertura REAL NOT NULL,
    entradas_count INTEGER NOT NULL DEFAULT 0,
    errores_count INTEGER NOT NULL DEFAULT 0,
    scan_id TEXT,
    created_at TEXT NOT NULL,
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

-- Clave unica por equipo/volumen/ruta normalizada y scan (3.8.5.1.4.2.5, .5.2).
-- Permite que la misma ruta exista en diferentes escaneos (linea base e
-- incremental) sin duplicarse dentro de un mismo scan.
CREATE UNIQUE INDEX IF NOT EXISTS idx_file_entries_unique_path_scan
    ON file_entries(machine_id, volume, normalized_path, scan_id);

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

-- Clave unica por equipo y volumen: solo puede existir una linea base (la
-- primera) para cada (machine_id, volumen), preservada como referencia
-- de cambios incrementales (3.8.5.1.4.5.1).
CREATE UNIQUE INDEX IF NOT EXISTS idx_lineas_base_unique_maquina_volumen
    ON lineas_base(machine_id, volume);
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
        # (3.8.5.1.4.2.11) Si la base de datos ya existe en disco, verificar su
        # integridad antes de tocarla. Una base corrupta no se inicializa sobre
        # ella: se intenta recuperar desde la copia de seguridad y, si no hay
        # una valida, se falla en alto sin destruir datos recuperables. Nunca
        # se sobrescribe una base valida con una vacia o incompleta tras un error.
        if self.db_path.exists():
            integridad = self.verify_integrity()
            if not integridad["ok"]:
                try:
                    self.restaurar_desde_backup()
                except InventoryBackupError:
                    raise InventoryCorruptError(
                        "La base de datos del inventario esta corrupta y no se "
                        "pudo recuperar desde copia de seguridad: "
                        f"{integridad.get('error')}"
                    ) from None
                if not self.verify_integrity()["ok"]:
                    raise InventoryCorruptError(
                        "La copia de seguridad restaurada tampoco pasa la "
                        "verificacion de integridad."
                    )
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
    # Copia de seguridad, deteccion de corrupcion y recuperacion (3.8.5.1.4.2.11).
    # ------------------------------------------------------------------ #
    def backup_path(self, custom: Optional[Path] = None) -> Path:
        """Devuelve la ruta de la copia de seguridad del inventario.

        Por defecto queda junto a la base de datos SQLite con el sufijo
        `.bak` (p. ej. `data/system_inventory.sqlite3.bak`). Se acepta una
        ruta personalizada para entornos de prueba o configurados.
        """
        if custom is not None:
            return Path(custom)
        return self.db_path.parent / (self.db_path.name + DEFAULT_BACKUP_SUFFIX)

    def create_backup(self, backup_path: Optional[Path] = None) -> Path:
        """Crea una copia de seguridad del fichero SQLite actual.

        Usa `sqlite3.Connection.backup` para copiar la base en caliente de
        forma consistente (incluye el modo WAL). Si la base de datos no
        existe, no hay nada que respaldar y se levanta
        `InventoryBackupError`. Cualquier fallo se reporta como
        `InventoryBackupError` sin dejar un fichero de copia parcial
        presentado como valido.
        """
        dest = self.backup_path(backup_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            raise InventoryBackupError(
                f"No existe la base de datos para respaldar: {self.db_path}"
            )
        conn = self.connect()
        dest_conn: Optional[sqlite3.Connection] = None
        try:
            dest_conn = sqlite3.connect(str(dest))
            conn.backup(dest_conn)
            dest_conn.commit()
        except Exception:
            if dest_conn is not None:
                try:
                    dest_conn.close()
                except Exception:
                    pass
            # No dejar un fichero de copia parcial presentado como valido.
            try:
                if dest.exists():
                    dest.unlink()
            except OSError:
                pass
            raise InventoryBackupError(
                f"No se pudo crear la copia de seguridad en {dest}"
            ) from None
        finally:
            if dest_conn is not None:
                try:
                    dest_conn.close()
                except Exception:
                    pass
        return dest

    def verify_integrity(self) -> dict:
        """Diagnostica la integridad de la base de datos actual sin repararla.

        Ejecuta `PRAGMA quick_check` y `PRAGMA integrity_check` y devuelve un
        diccionario con el resultado de cada una, una bandera `ok` (True solo
        si ambas devuelven "ok") y, en caso de fallo, el motivo en `error`.
        Si la base de datos no existe o no se puede abrir, devuelve
        `ok=False` con el motivo sin levantar excepcion, para que el llamante
        decida si restaurar desde copia de seguridad o inicializar de cero.
        """
        resultado: dict[str, object] = {
            "quick_check": None,
            "integrity_check": None,
            "ok": False,
            "error": None,
        }
        if not self.db_path.exists():
            resultado["error"] = f"La base de datos no existe: {self.db_path}"
            return resultado
        try:
            conn = self.connect()
        except sqlite3.DatabaseError as exc:
            resultado["error"] = str(exc)
            resultado["ok"] = False
            return resultado
        try:
            cur = conn.execute("PRAGMA quick_check")
            resultado["quick_check"] = str(cur.fetchone()[0])
            cur = conn.execute("PRAGMA integrity_check")
            resultado["integrity_check"] = str(cur.fetchone()[0])
            resultado["ok"] = (
                resultado["quick_check"] == "ok"
                and resultado["integrity_check"] == "ok"
            )
        except sqlite3.DatabaseError as exc:
            resultado["error"] = str(exc)
            resultado["ok"] = False
        return resultado

    def restaurar_desde_backup(self, backup_path: Optional[Path] = None) -> None:
        """Restaura la base de datos actual desde una copia de seguridad.

        Antes de tocar la base actual, verifica que la copia de seguridad
        exista y pase `PRAGMA integrity_check`. Nunca se sobrescribe una base
        actual valida con una copia vacia, incompleta o corrupta: si la copia
        de seguridad no pasa la verificacion, se levanta
        `InventoryBackupError` y la base actual queda intacta. Si no existe
        copia de seguridad, tambien se levanta `InventoryBackupError`.
        """
        src = self.backup_path(backup_path)
        if not src.exists():
            raise InventoryBackupError(
                f"No existe copia de seguridad para restaurar: {src}"
            )
        # Verificar que la copia de seguridad sea valida antes de tocar la actual.
        tmp_conn: Optional[sqlite3.Connection] = None
        try:
            tmp_conn = sqlite3.connect(str(src))
            cur = tmp_conn.execute("PRAGMA integrity_check")
            status = str(cur.fetchone()[0])
        except sqlite3.DatabaseError as exc:
            if tmp_conn is not None:
                tmp_conn.close()
            raise InventoryBackupError(
                f"La copia de seguridad esta corrupta ({exc}); no se restaura sobre la base actual."
            ) from None
        finally:
            if tmp_conn is not None:
                tmp_conn.close()
        if status != "ok":
            raise InventoryBackupError(
                f"La copia de seguridad no pasa integrity_check ({status}); "
                f"no se restaura sobre la base actual."
            )
        # Cerrar la conexion actual antes de reemplazar el fichero.
        self.close()
        try:
            for suf in ("", "-wal", "-shm"):
                p = Path(str(self.db_path) + suf)
                if p.exists():
                    p.unlink()
            shutil.copy2(src, self.db_path)
        except Exception:
            raise InventoryBackupError(
                f"No se pudo restaurar desde {src} sobre {self.db_path}"
            ) from None
        # Reabrir la base restaurada.
        self.connect()

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
    # Linea base (primera instantanea completa por volumen) (3.8.5.1.4.5.1).
    # ------------------------------------------------------------------ #
    def registrar_linea_base_volumen(
        self,
        machine_id: str,
        volume: str,
        estado_volumen: str,
        cobertura: float,
        entradas_count: int = 0,
        errores_count: int = 0,
        scan_id: Optional[str] = None,
        fecha_base: Optional[str] = None,
    ) -> Optional[dict]:
        """Registra la primera linea base (instantanea completa) de un volumen.

        Solo se crea una linea base por `(machine_id, volume)`: si ya existe
        una linea base para ese equipo y volumen, no se sobrescribe y se
        devuelve la existente. De esta forma se conserva la fecha, el estado
        y la cobertura de la primera instantanea completa como referencia
        para la deteccion de cambios incrementales (3.8.5.1.4.5.1).

        `estado_volumen` es el estado diferenciado del volumen observado en
        el primer escaneo completo (p. ej. un valor de `EstadoVolumen`).
        `cobertura` es el porcentaje de avance del recorrido (0.0 a 100.0).
        `scan_id`, cuando se proporciona, vincula la linea base con la
        ejecucion de escaneo que la genero. `fecha_base` permite fijar la
        fecha de la linea base (por defecto, la fecha actual).

        Retorna el diccionario de la linea base (la creada o la ya existente)
        o None si no se pudo registrar.
        """
        if fecha_base is None:
            fecha_base = _now_iso()
        created_at = _now_iso()
        linea_id = str(uuid.uuid4())
        self.record_machine(machine_id, created_at=fecha_base)
        conn = self.connect()
        existente = conn.execute(
            "SELECT * FROM lineas_base WHERE machine_id = ? AND volume = ?",
            (machine_id, volume),
        ).fetchone()
        if existente is not None:
            return dict(existente)
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Re-comprobar dentro de la transaccion para evitar duplicados
            # por concurrencia entre la lectura y la insercion.
            existente = conn.execute(
                "SELECT * FROM lineas_base WHERE machine_id = ? AND volume = ?",
                (machine_id, volume),
            ).fetchone()
            if existente is not None:
                conn.rollback()
                return dict(existente)
            conn.execute(
                """
                INSERT INTO lineas_base(
                    linea_id, machine_id, volume, fecha_base, estado_volumen,
                    cobertura, entradas_count, errores_count, scan_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    linea_id,
                    machine_id,
                    volume,
                    fecha_base,
                    estado_volumen,
                    float(cobertura),
                    int(entradas_count),
                    int(errores_count),
                    scan_id,
                    created_at,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.obtener_linea_base_volumen(machine_id, volume)

    def obtener_linea_base_volumen(self, machine_id: str, volume: str) -> Optional[dict]:
        """Devuelve la linea base (primera instantanea completa) de un volumen.

        Retorna el diccionario con `linea_id`, `machine_id`, `volume`,
        `fecha_base`, `estado_volumen`, `cobertura`, `entradas_count`,
        `errores_count`, `scan_id` y `created_at`, o None si no existe una
        linea base para ese equipo y volumen.
        """
        conn = self.connect()
        cur = conn.execute(
            "SELECT * FROM lineas_base WHERE machine_id = ? AND volume = ?",
            (machine_id, volume),
        )
        row = cur.fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------ #
    # Deteccion de cambios incrementales (3.8.5.1.4.5.2).
    # ------------------------------------------------------------------ #

    @dataclass
    class CambioEntrada:
        """Describe un cambio detectado en una entrada entre la linea base y un escaneo nuevo."""

        normalized_path: str
        absolute_path: str
        name: str
        entry_type: str
        campo: str
        valor_base: object
        valor_nuevo: object

    @dataclass
    class ResultadoCambiosIncrementales:
        """Resultado completo de la deteccion de cambios incrementales."""

        machine_id: str
        volume: str
        linea_base: Optional[dict]
        scan_usado: Optional[dict]
        altas: list[dict] = field(default_factory=list)
        cambios: list[CambioEntrada] = field(default_factory=list)
        desapariciones: list[dict] = field(default_factory=list)
        sin_cambios: int = 0
        total_base: int = 0
        total_nuevo: int = 0

        def resumen(self) -> dict:
            """Devuelve un resumen serializable del resultado."""
            return {
                "machine_id": self.machine_id,
                "volume": self.volume,
                "linea_base_id": self.linea_base["linea_id"] if self.linea_base else None,
                "scan_usado_id": self.scan_usado["scan_id"] if self.scan_usado else None,
                "altas": len(self.altas),
                "cambios": len(self.cambios),
                "desapariciones": len(self.desapariciones),
                "sin_cambios": self.sin_cambios,
                "total_base": self.total_base,
                "total_nuevo": self.total_nuevo,
            }

    def _obtener_entradas_escaneo(self, scan_id: str) -> list[dict]:
        """Devuelve todas las entradas de archivo de una ejecucion de escaneo dada,
        indexadas por ruta normalizada."""
        conn = self.connect()
        cur = conn.execute(
            """
            SELECT entry_id, scan_id, machine_id, volume, absolute_path,
                   normalized_path, relative_path, name, extension, entry_type,
                   size_bytes, modified_at, created_at, accessed_at, attributes,
                   excluded, source, last_checked_at
            FROM file_entries WHERE scan_id = ?
            ORDER BY normalized_path
            """,
            (scan_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def _campos_metadata_comparables(self) -> tuple[str, ...]:
        """Campos de metadatos comparables para detectar cambios entre escaneos.

        Se comparan tamaño, marcas temporales y atributos. Nunca el contenido
        del archivo (privacidad, 3.8.5.1.4.1.9).
        """
        return ("size_bytes", "modified_at", "created_at", "accessed_at", "attributes")

    def detectar_cambios_incrementales(
        self,
        machine_id: str,
        volume: str,
        scan_id_nuevo: Optional[str] = None,
    ) -> ResultadoCambiosIncrementales:
        """Detecta altas, cambios y desapariciones entre la linea base y un escaneo nuevo.

        La comparacion se hace por `normalized_path` como clave unica, usando
        solo metadatos observados del SO (tamaño, marcas temporales, atributos).
        Nunca se lee ni compara el contenido de archivos.

        Flujo:
        1. Obtiene la linea base para (machine_id, volume). Si no existe,
           retorna un resultado vacio con `linea_base=None`.
        2. Si `scan_id_nuevo` no se indica, usa el ultimo escaneo del equipo y
           volumen.
        3. Recupera las entradas de archivo del escaneo de la linea base y del
           escaneo nuevo.
        4. Compara por normalized_path:
           - **Altas**: presentes en el nuevo, ausentes en la base.
           - **Desapariciones**: presentes en la base, ausentes en el nuevo.
           - **Cambios**: presentes en ambas pero con metadatos diferentes.
           - **Sin cambios**: presentes en ambas con metadatos identicos.

        Retorna un `ResultadoCambiosIncrementales` con listas de altas,
        cambios (con campo, valor_base y valor_nuevo), desapariciones y
        contadores de sin cambios, total_base y total_nuevo.
        """
        linea_base = self.obtener_linea_base_volumen(machine_id, volume)
        if linea_base is None:
            return self.ResultadoCambiosIncrementales(
                machine_id=machine_id,
                volume=volume,
                linea_base=None,
                scan_usado=None,
            )

        # Determinar el escaneo nuevo a comparar.
        if scan_id_nuevo is not None:
            scan_usado = self.get_scan_run(scan_id_nuevo)
            if scan_usado is None or scan_usado["machine_id"] != machine_id or scan_usado["volume"] != volume:
                raise ValueError(
                    f"El scan_id {scan_id_nuevo!r} no pertenece a "
                    f"machine_id={machine_id!r}, volume={volume!r}."
                )
        else:
            scan_usado = self.get_latest_scan(machine_id, volume)
            if scan_usado is None:
                return self.ResultadoCambiosIncrementales(
                    machine_id=machine_id,
                    volume=volume,
                    linea_base=linea_base,
                    scan_usado=None,
                )
            # Si el ultimo escaneo es el mismo que genero la linea base, no hay
            # un escaneo nuevo distinto con el que comparar.
            scan_base_id = linea_base.get("scan_id")
            if scan_usado["scan_id"] == scan_base_id:
                return self.ResultadoCambiosIncrementales(
                    machine_id=machine_id,
                    volume=volume,
                    linea_base=linea_base,
                    scan_usado=None,
                )

        scan_base_id = linea_base.get("scan_id")
        scan_nuevo_id = scan_usado["scan_id"]

        # Recuperar entradas de ambos escaneos.
        entradas_base = self._obtener_entradas_escaneo(scan_base_id) if scan_base_id else []
        entradas_nuevo = self._obtener_entradas_escaneo(scan_nuevo_id)

        # Indexar por normalized_path.
        base_por_ruta: dict[str, dict] = {}
        for e in entradas_base:
            base_por_ruta[e["normalized_path"]] = e

        nuevo_por_ruta: dict[str, dict] = {}
        for e in entradas_nuevo:
            nuevo_por_ruta[e["normalized_path"]] = e

        campos = self._campos_metadata_comparables()

        resultado = self.ResultadoCambiosIncrementales(
            machine_id=machine_id,
            volume=volume,
            linea_base=linea_base,
            scan_usado=scan_usado,
            total_base=len(base_por_ruta),
            total_nuevo=len(nuevo_por_ruta),
        )

        # Altas: en el nuevo pero no en la base.
        for ruta, e_nuevo in nuevo_por_ruta.items():
            if ruta not in base_por_ruta:
                resultado.altas.append(e_nuevo)

        # Desapariciones: en la base pero no en el nuevo.
        for ruta, e_base in base_por_ruta.items():
            if ruta not in nuevo_por_ruta:
                resultado.desapariciones.append(e_base)

        # Cambios / sin cambios: en ambas.
        for ruta in base_por_ruta.keys() & nuevo_por_ruta.keys():
            e_base = base_por_ruta[ruta]
            e_nuevo = nuevo_por_ruta[ruta]
            campo_cambiado = None
            for campo in campos:
                v_base = e_base.get(campo)
                v_nuevo = e_nuevo.get(campo)
                # attributes se almacena como JSON string; comparar como lista.
                if campo == "attributes":
                    try:
                        v_base_cmp = json.loads(v_base) if isinstance(v_base, str) else (v_base or [])
                    except (json.JSONDecodeError, TypeError):
                        v_base_cmp = v_base
                    try:
                        v_nuevo_cmp = json.loads(v_nuevo) if isinstance(v_nuevo, str) else (v_nuevo or [])
                    except (json.JSONDecodeError, TypeError):
                        v_nuevo_cmp = v_nuevo
                    if v_base_cmp != v_nuevo_cmp:
                        campo_cambiado = campo
                        break
                else:
                    if v_base != v_nuevo:
                        campo_cambiado = campo
                        break
            if campo_cambiado is not None:
                vb = e_base.get(campo_cambiado)
                vn = e_nuevo.get(campo_cambiado)
                if campo_cambiado == "attributes":
                    try:
                        vb = json.loads(vb) if isinstance(vb, str) else (vb or [])
                    except (json.JSONDecodeError, TypeError):
                        vb = vb
                    try:
                        vn = json.loads(vn) if isinstance(vn, str) else (vn or [])
                    except (json.JSONDecodeError, TypeError):
                        vn = vn
                resultado.cambios.append(
                    self.CambioEntrada(
                        normalized_path=ruta,
                        absolute_path=e_nuevo["absolute_path"],
                        name=e_nuevo["name"],
                        entry_type=e_nuevo["entry_type"],
                        campo=campo_cambiado,
                        valor_base=vb,
                        valor_nuevo=vn,
                    )
                )
            else:
                resultado.sin_cambios += 1

        return resultado

    # ------------------------------------------------------------------ #
    # Deteccion de renombrados / cambios de ruta o nombre (3.8.5.1.4.5.3).
    # ------------------------------------------------------------------ #

    @dataclass
    class RenombradoDetectado:
        """Describe un renombrado detectado entre el escaneo base y un escaneo nuevo.

        Se registra solo cuando el sistema de archivos proporciona evidencia
        suficiente: los metadatos observados (tamaño, marcas temporales,
        atributos y tipo de entrada) coinciden en ambas rutas, por lo que es
        razonable tratar la entrada como el mismo archivo movido o renombrado,
        y no como una eliminacion más una alta. Nunca se fusionan archivos
        distintos solo por compartir nombre o tamaño.
        """

        normalized_path_base: str
        normalized_path_nuevo: str
        absolute_path_base: str
        absolute_path_nuevo: str
        name_base: str
        name_nuevo: str
        entry_type: str
        size_bytes: int
        campos_coincidentes: list[str]
        nombre_cambio: bool
        ruta_cambio: bool

    @dataclass
    class ResultadoDeteccionRenombrados:
        """Resultado completo de la detección de renombrados entre un escaneo
        base y uno nuevo."""

        machine_id: str
        volume: str
        linea_base: Optional[dict]
        scan_usado: Optional[dict]
        renombrados: list[RenombradoDetectado] = field(default_factory=list)
        altas: list[dict] = field(default_factory=list)
        desapariciones: list[dict] = field(default_factory=list)
        sin_cambios: int = 0
        total_base: int = 0
        total_nuevo: int = 0

        def resumen(self) -> dict:
            """Devuelve un resumen serializable del resultado."""
            return {
                "machine_id": self.machine_id,
                "volume": self.volume,
                "linea_base_id": self.linea_base["linea_id"] if self.linea_base else None,
                "scan_usado_id": self.scan_usado["scan_id"] if self.scan_usado else None,
                "renombrados": len(self.renombrados),
                "altas": len(self.altas),
                "desapariciones": len(self.desapariciones),
                "sin_cambios": self.sin_cambios,
                "total_base": self.total_base,
                "total_nuevo": self.total_nuevo,
            }

    def _valor_comparable(self, valor: object, campo: str) -> object:
        """Devuelve un valor comparable para metadatos de una entrada de archivo.

        `attributes` se almacena como JSON string y se compara como lista; el
        resto se compara tal cual. Los valores ausentes (None) se devuelven
        como None para que el llamante decida si son evidencia suficiente.
        """
        if campo == "attributes":
            try:
                return json.loads(valor) if isinstance(valor, str) else (valor or [])
            except (json.JSONDecodeError, TypeError):
                return valor
        return valor

    def _campos_requisitos_renombrado(self) -> tuple[str, ...]:
        """Campos que deben estar presentes y coincidir como evidencia mínima
        de que una ruta base y una ruta nueva son el mismo archivo renombrado.

        Son los metadatos más estables ante un cambio de nombre o de ruta:
        tamaño y marca temporal de modificacion. Sin ellos no hay evidencia
        suficiente para emparejar una desaparición con una alta.
        """
        return ("size_bytes", "modified_at")

    def _metadatos_coinciden(
        self, e_base: dict, e_nuevo: dict
    ) -> tuple[bool, list[str]]:
        """Comprueba si dos entradas comparten evidencia suficiente de ser el
        mismo archivo renombrado.

        Requisitos:
        - Los campos requeridos (`size_bytes`, `modified_at`) deben estar
          presentes (no None) en ambas y coincidir.
        - Todos los demás campos comparables disponibles (no None en ambas)
          deben coincidir también: `created_at`, `accessed_at`, `attributes`,
          `entry_type`.
        - Nunca se empareja solo por nombre ni solo por tamaño: ambos campos
          requeridos y todos los disponibles deben concordar.
        """
        campos = self._campos_metadata_comparables()
        requeridos = self._campos_requisitos_renombrado()
        coincidentes: list[str] = []
        for campo in campos:
            v_base = self._valor_comparable(e_base.get(campo), campo)
            v_nuevo = self._valor_comparable(e_nuevo.get(campo), campo)
            disponible = v_base is not None and v_nuevo is not None
            if campo in requeridos:
                # Campo obligatorio: debe estar en ambos y coincidir.
                if not disponible or v_base != v_nuevo:
                    return False, coincidentes
                coincidentes.append(campo)
            elif disponible:
                # Campo opcional: si esta disponible en ambos, debe coincidir.
                if v_base != v_nuevo:
                    return False, coincidentes
                coincidentes.append(campo)
        return True, coincidentes

    def detectar_renombrados(
        self,
        machine_id: str,
        volume: str,
        scan_id_nuevo: Optional[str] = None,
    ) -> ResultadoDeteccionRenombrados:
        """Detecta cambios de ruta y renombrados entre la línea base y un
        escaneo nuevo.

        Reutiliza `detectar_cambios_incrementales` para obtener altas,
        desapariciones y sin cambios. Luego empareja cada desaparición del
        escaneo base con una alta del escaneo nuevo solo cuando hay evidencia
        suficiente de que se trata del mismo archivo (tamaño y marca temporal
        de modificación presentes e iguales, y todos los demás metadatos
        disponibles coincidentes). Los emparejamientos aceptados se reportan
        como renombrados y dejan de contarse como alta ni desaparición; el
        resto se reporta como alta o desaparición genuina.

        Nunca fusiona archivos distintos solo por compartir nombre o tamaño:
        sin los metadatos requeridos coincidentes, no hay renombrado.

        Retorna un `ResultadoDeteccionRenombrados` con listas de renombrados,
        altas no emparejadas y desapariciones no emparejadas.
        """
        base = self.detectar_cambios_incrementales(
            machine_id, volume, scan_id_nuevo=scan_id_nuevo
        )
        linea_base = base.linea_base
        scan_usado = base.scan_usado

        # Indexar desapariciones (base) y altas (nuevo) por ruta normalizada.
        desapariciones: list[dict] = list(base.desapariciones)
        altas: list[dict] = list(base.altas)
        altas_usadas: set[int] = set()
        renombrados: list[self.RenombradoDetectado] = []

        # Determinista: procesar desapariciones ordenadas por ruta.
        for e_base in sorted(desapariciones, key=lambda e: str(e.get("normalized_path", ""))):
            mejor_idx: Optional[int] = None
            mejor_coincidentes: list[str] = []
            for idx, e_nuevo in enumerate(altas):
                if idx in altas_usadas:
                    continue
                coinciden, campos = self._metadatos_coinciden(e_base, e_nuevo)
                if not coinciden:
                    continue
                if mejor_idx is None or len(campos) > len(mejor_coincidentes):
                    mejor_idx = idx
                    mejor_coincidentes = campos
            if mejor_idx is None:
                continue
            e_nuevo = altas[mejor_idx]
            altas_usadas.add(mejor_idx)
            nombre_cambio = str(e_base.get("name", "")) != str(e_nuevo.get("name", ""))
            ruta_cambio = str(e_base.get("normalized_path", "")) != str(
                e_nuevo.get("normalized_path", "")
            )
            renombrados.append(
                self.RenombradoDetectado(
                    normalized_path_base=str(e_base.get("normalized_path", "")),
                    normalized_path_nuevo=str(e_nuevo.get("normalized_path", "")),
                    absolute_path_base=str(e_base.get("absolute_path", "")),
                    absolute_path_nuevo=str(e_nuevo.get("absolute_path", "")),
                    name_base=str(e_base.get("name", "")),
                    name_nuevo=str(e_nuevo.get("name", "")),
                    entry_type=str(e_base.get("entry_type", "")),
                    size_bytes=int(e_base.get("size_bytes", 0) or 0),
                    campos_coincidentes=mejor_coincidentes,
                    nombre_cambio=nombre_cambio,
                    ruta_cambio=ruta_cambio,
                )
            )

        altas_no_emparejadas = [
            e for idx, e in enumerate(altas) if idx not in altas_usadas
        ]
        # Las desapariciones emparejadas son las usadas en renombrados.
        rutas_base_emparejadas = {r.normalized_path_base for r in renombrados}
        desapariciones_no_emparejadas = [
            e
            for e in desapariciones
            if str(e.get("normalized_path", "")) not in rutas_base_emparejadas
        ]

        return self.ResultadoDeteccionRenombrados(
            machine_id=machine_id,
            volume=volume,
            linea_base=linea_base,
            scan_usado=scan_usado,
            renombrados=renombrados,
            altas=altas_no_emparejadas,
            desapariciones=desapariciones_no_emparejadas,
            sin_cambios=base.sin_cambios,
            total_base=base.total_base,
            total_nuevo=base.total_nuevo,
        )

    # ------------------------------------------------------------------ #
    # Marcado de entradas ausentes / eliminadas (3.8.5.1.4.5.4).
    # ------------------------------------------------------------------ #

    def marcar_entradas_eliminadas(
        self,
        machine_id: str,
        volume: str,
        scan_id_referencia: str,
        entradas_ausentes: list[dict],
        errores_escaneo: Optional[list[dict]] = None,
    ) -> dict:
        """
        Marca como ausente/eliminada las entradas indicadas solo despues de
        verificar que el escaneo de referencia (`scan_id_referencia`) del
        mismo equipo y volumen se completo correctamente con
        `SCAN_RESULT_OK`.

        Requisitos (3.8.5.1.4.5.4):
        - Una entrada solo se marca como ausente/eliminada cuando el escaneo
          del ambito que la contiene termino correctamente. Un escaneo
          parcial, interrumpido o con error no justifica marcar entradas
          como eliminadas: es posible que sigan existiendo pero no hayan
          sido inspeccionadas (3.8.5.1.4.4.9). La marca se persiste como
          `excluded = 1` en la entrada del escaneo base.
        - Un error de permisos no equivale a una eliminacion: si el escaneo
          registro `permiso_denegado` sobre una ruta, las entradas bajo esa
          ruta no se marcan como eliminadas (pueden seguir existiendo pero
          ser inaccesibles).

        `entradas_ausentes` es la lista de entradas (output de
        `detectar_cambios_incrementales` o `detectar_renombrados`) que
        desaparecieron del escaneo nuevo y se consideran candidatas a
        marcarse como eliminadas. Cada entrada debe llevar `scan_id`,
        `machine_id`, `volume` y `normalized_path`.

        `errores_escaneo` es una lista opcional de errores registrados durante
        el escaneo de referencia, cada uno con claves `ruta`, `categoria` y
        `mensaje`. Las entradas cuya ruta normalizada quede bajo un prefijo
        con categoria `permiso_denegado` no se marcan.

        Retorna un diccionario resumen con `marcadas`, `no_marcadas` (lista
        de {normalized_path, motivo}) y `total_entradas`.
        """
        # 1. Validar que el escaneo de referencia exista y pertenezca al
        #    equipo y volumen indicados.
        scan = self.get_scan_run(scan_id_referencia)
        if scan is None:
            raise ValueError(
                f"El escaneo de referencia {scan_id_referencia!r} no existe."
            )
        if scan["machine_id"] != machine_id or scan["volume"] != volume:
            raise ValueError(
                f"El escaneo {scan_id_referencia!r} no pertenece a "
                f"machine_id={machine_id!r}, volume={volume!r}."
            )

        # 2. Solo se marca despues de completar correctamente el escaneo del
        #    ambito (3.8.5.1.4.5.4). Resultado distinto de OK no autoriza
        #    marcar como eliminada.
        if scan["result"] != SCAN_RESULT_OK:
            motivo = (
                f"el escaneo de referencia no se completo correctamente "
                f"(resultado={scan['result']})"
            )
            no_marcadas = [
                {
                    "normalized_path": e.get("normalized_path", ""),
                    "motivo": motivo,
                }
                for e in entradas_ausentes
            ]
            return {
                "machine_id": machine_id,
                "volume": volume,
                "scan_id_referencia": scan_id_referencia,
                "resultado_scan": scan["result"],
                "marcadas": 0,
                "no_marcadas": no_marcadas,
                "total_entradas": len(entradas_ausentes),
            }

        # 3. Calcular prefijos de ruta con error de permiso (si se proveen
        #    errores). Un error de permisos no equivale a una eliminacion:
        #    las entradas bajo esos prefijos no se marcan.
        prefijos_permiso_denegado: set[str] = set()
        if errores_escaneo:
            for err in errores_escaneo:
                if str(err.get("categoria", "")) == "permiso_denegado":
                    ruta = err.get("ruta") or ""
                    if ruta:
                        prefijos_permiso_denegado.add(normalize_path(ruta))

        # 4. Marcar cada entrada ausente como eliminada (excluded = 1),
        #    salvo las que queden bajo un prefijo con permiso denegado o que
        #    no pertenezcan al equipo/volumen indicados.
        marcadas = 0
        no_marcadas: list[dict] = []
        ahora = _now_iso()

        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for e in entradas_ausentes:
                ruta_normalizada = e.get("normalized_path") or ""
                if not ruta_normalizada:
                    no_marcadas.append(
                        {
                            "normalized_path": "",
                            "motivo": "la entrada no tiene normalized_path",
                        }
                    )
                    continue

                # Permiso denegado sobre un ancestro => no es una eliminacion
                # confirmada (3.8.5.1.4.5.4).
                if self._ruta_bajo_prefijos(
                    ruta_normalizada, prefijos_permiso_denegado
                ):
                    no_marcadas.append(
                        {
                            "normalized_path": ruta_normalizada,
                            "motivo": "la ruta queda bajo un prefijo con error de permiso denegado; no equivale a eliminacion",
                        }
                    )
                    continue

                # La entrada debe pertenecer al mismo equipo y volumen.
                if str(e.get("machine_id", "")) != machine_id or str(
                    e.get("volume", "")
                ) != volume:
                    no_marcadas.append(
                        {
                            "normalized_path": ruta_normalizada,
                            "motivo": "la entrada no pertenece al equipo/volumen indicados",
                        }
                    )
                    continue

                scan_id_entrada = e.get("scan_id")
                if not scan_id_entrada:
                    no_marcadas.append(
                        {
                            "normalized_path": ruta_normalizada,
                            "motivo": "la entrada no tiene scan_id asociado",
                        }
                    )
                    continue

                cur = conn.execute(
                    """
                    UPDATE file_entries
                    SET excluded = 1,
                        last_checked_at = ?
                    WHERE machine_id = ? AND volume = ?
                      AND normalized_path = ? AND scan_id = ?
                    """,
                    (
                        ahora,
                        machine_id,
                        volume,
                        ruta_normalizada,
                        scan_id_entrada,
                    ),
                )
                if cur.rowcount == 0:
                    no_marcadas.append(
                        {
                            "normalized_path": ruta_normalizada,
                            "motivo": "no existe una entrada de archivo con esos identificadores",
                        }
                    )
                    continue
                marcadas += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "machine_id": machine_id,
            "volume": volume,
            "scan_id_referencia": scan_id_referencia,
            "resultado_scan": scan["result"],
            "marcadas": marcadas,
            "no_marcadas": no_marcadas,
            "total_entradas": len(entradas_ausentes),
        }

    @staticmethod
    def _ruta_bajo_prefijos(
        ruta_normalizada: str, prefijos: set[str]
    ) -> bool:
        """Devuelve True si `ruta_normalizada` queda bajo alguno de los
        prefijos indicados (el propio directorio o un archivo dentro de
        ese directorio)."""
        if not prefijos or not ruta_normalizada:
            return False
        for prefijo in prefijos:
            p = prefijo.rstrip("/")
            if ruta_normalizada == p or ruta_normalizada.startswith(p + "/"):
                return True
        return False

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
