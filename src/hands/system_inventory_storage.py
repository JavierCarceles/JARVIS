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

import psutil

from src.hands.application_preflight import (
    ApplicationPreflight,
    get_application_preflight,
)
from src.hands.system_inventory import (
    EntryType,
    EstadoCaducidad,
    InventoryEntry,
    ResultadoCaducidad,
    ResultadoValidacionDestino,
    esta_caducado,
    validar_destino,
)


SCHEMA_VERSION = 5

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


def _migracion_v4_a_v5(conn: sqlite3.Connection) -> None:
    """Migracion v4 -> v5: agrega columnas `version`, `producto` e `evidencia`
    a la tabla `application_candidates`.

    Estas columnas son necesarias para registrar, por cada candidato de
    aplicacion descubierto y clasificado (unidad 3.8.5.1.4.7.6):
    - version: version del producto leida de los recursos de version del
      archivo (cuando existe).
    - producto: nombre del producto / empresa leido de los recursos de
      version.
    - evidencia: lista serializada en JSON de las evidencias de clasificacion
      (archivo existente, encabezado PE valido, acceso directo resuelto,
      URI admitida, etc.).

    Es una operacion aditiva: conserva todas las filas existentes y les
    asigna NULL en las nuevas columnas. No elimina, ni reinterpreta, datos
    de inventarios de version anterior.
    """
    for columna, definicion in (
        ("version", "TEXT"),
        ("producto", "TEXT"),
        ("evidencia", "TEXT NOT NULL DEFAULT '[]'"),
    ):
        try:
            conn.execute(
                f"ALTER TABLE application_candidates ADD COLUMN {columna} {definicion}"
            )
        except sqlite3.OperationalError:
            # La columna ya existe (base creada ya en esquema v5): nada que migrar.
            pass


# (version_origen, version_destino, nombre, funcion_de_migracion)
_MIGRACIONES: list[tuple[int, int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, 2, "agregar normalized_path a file_entries", _migracion_v1_a_v2),
    (2, 3, "crear tabla lineas_base", _migracion_v2_a_v3),
    (3, 4, "clave unica de file_entries incluye scan_id", _migracion_v3_a_v4),
    (4, 5, "agregar version/producto/evidencia a application_candidates", _migracion_v4_a_v5),
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
    version TEXT,
    producto TEXT,
    evidencia TEXT NOT NULL DEFAULT '[]',
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

    def obtener_entradas_escaneo(self, scan_id: str) -> list[dict]:
        """Devuelve todas las entradas de archivo de una ejecución de escaneo dada.

        Expone de forma pública las entradas de un escaneo (mismo contenido que
        el método privado `_obtener_entradas_escaneo`) para que capas de
        decisión superiores —como la política de refresco (3.8.5.1.4.8.2)—
        puedan inspeccionar la última comprobación de cada entrada (por ejemplo,
        su `last_checked_at`) sin recurrir a miembros privados del almacenamiento.
        """
        return self._obtener_entradas_escaneo(scan_id)

    # ------------------------------------------------------------------ #
    # Reanudacion de escaneo interrumpido (3.8.5.1.4.5.5).
    # ------------------------------------------------------------------ #
    def reanudar_scan(
        self,
        scan_id: str,
        machine_id: str,
        volume: str,
    ) -> dict:
        """Reanuda un escaneo interrumpido usando el mismo scan_id (misma generacion).

        Valida que el scan exista, pertenezca al equipo y volumen indicados, y que
        este sin finalizar (finished_at IS NULL, resultado SCAN_RESULT_INTERRUPTED).
        Si el bloqueo de concurrencia de (machine_id, volumen) no esta ya activo
        (recuperacion tras cierre inesperado donde begin_scan_run lo habia
        adquirido pero end_scan_run nunca lo libero), se adquiere ahora. Si ya
        esta activo, es porque begin_scan_run inicio este mismo scan y no se
        llamo a end_scan_run: no se vuelve a adquirir, se deja retenido para
        seguir insertando entradas con el mismo scan_id.
        No degrada la linea base ni el ultimo escaneo con resultado OK: solo
        reactiva el scan existente para que se le puedan agregar mas entradas
        antes de finalizarlo con end_scan_run.

        El bloqueo, cuando se adquiere aqui, se libera en end_scan_run.

        Retorna el diccionario del scan reanudado.
        """
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM scan_runs WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        if row is None:
            raise ValueError(
                f"El scan_id {scan_id!r} no existe en el inventario."
            )
        row_dict = dict(row)
        if row_dict["machine_id"] != machine_id:
            raise ValueError(
                f"El scan {scan_id!r} pertenece al equipo "
                f"{row_dict['machine_id']!r}, no a {machine_id!r}."
            )
        if row_dict["volume"] != volume:
            raise ValueError(
                f"El scan {scan_id!r} pertenece al volumen "
                f"{row_dict['volume']!r}, no a {volume!r}."
            )
        if row_dict["finished_at"] is not None:
            raise ValueError(
                f"El scan {scan_id!r} ya esta finalizado (resultado "
                f"{row_dict['result']!r}) y no se puede reanudar. "
                "Solo un escaneo interrumpido sin finalizar se puede reanudar."
            )
        # Adquirir bloqueo solo si no esta ya activo para esta clave.
        if not self.has_active_scan(machine_id, volume):
            self._acquire_scan_lock(machine_id, volume)
        return row_dict

    # ------------------------------------------------------------------ #
    # Refresco bajo demanda y revalidacion de destino (3.8.5.1.4.5.6).
    # ------------------------------------------------------------------ #
    def refrescar_entrada_por_ruta(
        self,
        machine_id: str,
        volume: str,
        ruta_absoluta: str,
    ) -> dict:
        """Refresca (revalida puntualmente) una única ruta del inventario.

        Parte de la última ejecución de escaneo del equipo y volumen,
        normaliza la ruta y localiza la entrada correspondiente. Comprueba en
        el sistema de archivos si el destino sigue existiendo y si su tamaño
        cambió respecto a lo almacenado. Actualiza `last_checked_at` de la
        entrada sin crear un nuevo escaneo ni una nueva generación.

        No marca la entrada como eliminada si ya no existe: esa decisión
        corresponde a 3.8.5.1.4.5.4 y requiere un escaneo de referencia con
        resultado `SCAN_RESULT_OK`.

        Retorna un diccionario con `ruta`, `normalized_path`, `scan_id`,
        `existe_ahora`, `cambio_detectado`, `last_checked_at`,
        `entradas_refrescadas` y `razon`.
        """
        if not ruta_absoluta or not isinstance(ruta_absoluta, str):
            return {
                "ruta": ruta_absoluta,
                "normalized_path": "",
                "machine_id": machine_id,
                "volume": volume,
                "scan_id": None,
                "existe_ahora": False,
                "cambio_detectado": False,
                "last_checked_at": None,
                "entradas_refrescadas": 0,
                "razon": "Ruta vacía o no es una cadena.",
            }

        self.record_machine(machine_id)
        scan = self.get_latest_scan(machine_id, volume)
        if scan is None:
            return {
                "ruta": ruta_absoluta,
                "normalized_path": normalize_path(ruta_absoluta),
                "machine_id": machine_id,
                "volume": volume,
                "scan_id": None,
                "existe_ahora": False,
                "cambio_detectado": False,
                "last_checked_at": None,
                "entradas_refrescadas": 0,
                "razon": "No hay escaneo previo para este equipo y volumen.",
            }

        normalized_path = normalize_path(ruta_absoluta)
        scan_id = scan["scan_id"]
        ahora = _now_iso()

        conn = self.connect()
        cur = conn.execute(
            """
            SELECT entry_id, absolute_path, size_bytes
            FROM file_entries
            WHERE machine_id = ? AND volume = ? AND scan_id = ?
              AND normalized_path = ?
            """,
            (machine_id, volume, scan_id, normalized_path),
        )
        filas = cur.fetchall()
        if not filas:
            return {
                "ruta": ruta_absoluta,
                "normalized_path": normalized_path,
                "machine_id": machine_id,
                "volume": volume,
                "scan_id": scan_id,
                "existe_ahora": False,
                "cambio_detectado": False,
                "last_checked_at": None,
                "entradas_refrescadas": 0,
                "razon": "La ruta no está registrada en el último escaneo de este volumen.",
            }

        existe_ahora = False
        cambio_detectado = False
        entradas_refrescadas = 0
        try:
            conn.execute("BEGIN IMMEDIATE")
            for fila in filas:
                absolute_path = fila["absolute_path"]
                existe = os.path.exists(absolute_path)
                cambio = False
                if existe:
                    existe_ahora = True
                    try:
                        stat = os.stat(absolute_path)
                        if int(fila["size_bytes"] or 0) != int(stat.st_size):
                            cambio = True
                    except OSError:
                        # Existe pero no se pueden leer sus metadatos.
                        pass
                if cambio:
                    cambio_detectado = True
                cur.execute(
                    """
                    UPDATE file_entries
                    SET last_checked_at = ?
                    WHERE entry_id = ? AND scan_id = ?
                    """,
                    (ahora, fila["entry_id"], scan_id),
                )
                entradas_refrescadas += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "ruta": ruta_absoluta,
            "normalized_path": normalized_path,
            "machine_id": machine_id,
            "volume": volume,
            "scan_id": scan_id,
            "existe_ahora": existe_ahora,
            "cambio_detectado": cambio_detectado,
            "last_checked_at": ahora,
            "entradas_refrescadas": entradas_refrescadas,
            "razon": None,
        }

    def refrescar_volumen(
        self,
        machine_id: str,
        volume: str,
    ) -> dict:
        """Refresca todas las entradas de un volumen.

        Revalida puntualmente cada entrada del último escaneo del volumen:
        comprueba si sigue existiendo en el sistema de archivos y si su
        tamaño cambió, y actualiza `last_checked_at` de cada una. No crea un
        nuevo escaneo ni una nueva generación, y no marca entradas como
        eliminadas.

        Retorna un resumen con `machine_id`, `volume`, `scan_id`, `total`,
        `existentes`, `no_existentes`, `cambios_detectados`,
        `entradas_refrescadas`, `last_checked_at` y `razon`.
        """
        self.record_machine(machine_id)
        scan = self.get_latest_scan(machine_id, volume)
        if scan is None:
            return {
                "machine_id": machine_id,
                "volume": volume,
                "scan_id": None,
                "total": 0,
                "existentes": 0,
                "no_existentes": 0,
                "cambios_detectados": 0,
                "entradas_refrescadas": 0,
                "last_checked_at": None,
                "razon": "No hay escaneo previo para este equipo y volumen.",
            }

        scan_id = scan["scan_id"]
        ahora = _now_iso()
        entradas = self._obtener_entradas_escaneo(scan_id)

        existentes = 0
        no_existentes = 0
        cambios_detectados = 0
        entradas_refrescadas = 0

        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for e in entradas:
                absolute_path = e.get("absolute_path", "")
                existe = os.path.exists(absolute_path)
                cambio = False
                if existe:
                    existentes += 1
                    try:
                        stat = os.stat(absolute_path)
                        if int(e.get("size_bytes") or 0) != int(stat.st_size):
                            cambio = True
                    except OSError:
                        pass
                else:
                    no_existentes += 1
                if cambio:
                    cambios_detectados += 1
                conn.execute(
                    """
                    UPDATE file_entries
                    SET last_checked_at = ?
                    WHERE entry_id = ? AND scan_id = ?
                    """,
                    (ahora, e["entry_id"], scan_id),
                )
                entradas_refrescadas += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "machine_id": machine_id,
            "volume": volume,
            "scan_id": scan_id,
            "total": entradas_refrescadas,
            "existentes": existentes,
            "no_existentes": no_existentes,
            "cambios_detectados": cambios_detectados,
            "entradas_refrescadas": entradas_refrescadas,
            "last_checked_at": ahora,
            "razon": None,
        }

    def refrescar_incremental_global(self, machine_id: str) -> dict:
        """Refresco incremental global de todos los volúmenes de un equipo.

        Revalida puntualmente cada volumen conocido del equipo aplicando el
        mismo comportamiento que `refrescar_volumen` a cada uno, sin crear
        nuevos escaneos ni nuevas generaciones.

        Retorna un resumen agregado por equipo con el detalle por volumen en
        `por_volumen`.
        """
        self.record_machine(machine_id)
        conn = self.connect()
        cur = conn.execute(
            "SELECT DISTINCT volume FROM volumes WHERE machine_id = ? ORDER BY volume",
            (machine_id,),
        )
        volumes = [row["volume"] for row in cur.fetchall()]

        total = 0
        existentes = 0
        no_existentes = 0
        cambios_detectados = 0
        entradas_refrescadas = 0
        por_volumen = []
        for volume in volumes:
            resultado = self.refrescar_volumen(machine_id, volume)
            por_volumen.append(
                {
                    "volume": volume,
                    "total": resultado["total"],
                    "existentes": resultado["existentes"],
                    "no_existentes": resultado["no_existentes"],
                    "cambios_detectados": resultado["cambios_detectados"],
                }
            )
            total += resultado["total"]
            existentes += resultado["existentes"]
            no_existentes += resultado["no_existentes"]
            cambios_detectados += resultado["cambios_detectados"]
            entradas_refrescadas += resultado["entradas_refrescadas"]

        return {
            "machine_id": machine_id,
            "total_volumenes": len(volumes),
            "total": total,
            "existentes": existentes,
            "no_existentes": no_existentes,
            "cambios_detectados": cambios_detectados,
            "entradas_refrescadas": entradas_refrescadas,
            "por_volumen": por_volumen,
            "last_checked_at": _now_iso(),
        }

    def revalidar_destino_aplicacion(
        self,
        machine_id: str,
        volume: str,
        ruta: str,
    ) -> dict:
        """Revalida puntualmente el destino de una aplicación antes de abrirla.

        Comprueba si el destino sigue existiendo en el sistema de archivos y
        si es un archivo lanzable (no un directorio). Actualiza
        `last_checked_at` de la entrada del inventario cuando la ruta está
        registrada en el último escaneo del volumen.

        No lanza la aplicación ni abre nada; solo devuelve el resultado de la
        revalidación para que el flujo de apertura decida si procede.

        Retorna un diccionario con `valido`, `existe`, `es_archivo`, `ruta`,
        `normalized_path`, `scan_id`, `last_checked_at`,
        `entradas_refrescadas` y `razon`.
        """
        if not ruta or not isinstance(ruta, str):
            return {
                "valido": False,
                "existe": False,
                "es_archivo": False,
                "ruta": ruta,
                "normalized_path": "",
                "machine_id": machine_id,
                "volume": volume,
                "scan_id": None,
                "last_checked_at": None,
                "entradas_refrescadas": 0,
                "razon": "Destino vacío o no es una cadena.",
            }

        self.record_machine(machine_id)
        scan = self.get_latest_scan(machine_id, volume)
        scan_id = scan["scan_id"] if scan is not None else None
        ahora = _now_iso()
        normalized_path = normalize_path(ruta)

        ruta_resuelta = os.path.abspath(ruta)
        existe = os.path.exists(ruta_resuelta)
        es_archivo = existe and os.path.isfile(ruta_resuelta)
        valido = existe and es_archivo

        entradas_refrescadas = 0
        if scan_id is not None:
            conn = self.connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    """
                    UPDATE file_entries
                    SET last_checked_at = ?
                    WHERE machine_id = ? AND volume = ? AND scan_id = ?
                      AND normalized_path = ?
                    """,
                    (ahora, machine_id, volume, scan_id, normalized_path),
                )
                entradas_refrescadas = cur.rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        razon = None
        if not valido:
            if not existe:
                razon = "El destino no existe en el sistema de archivos."
            else:
                razon = "El destino no es un archivo lanzable (es un directorio o no es accesible)."

        return {
            "valido": valido,
            "existe": existe,
            "es_archivo": es_archivo,
            "ruta": ruta,
            "normalized_path": normalized_path,
            "machine_id": machine_id,
            "volume": volume,
            "scan_id": scan_id,
            "last_checked_at": ahora,
            "entradas_refrescadas": entradas_refrescadas,
            "razon": razon,
        }

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

        Cada candidato puede incluir opcionalmente `version`, `producto` e
        `evidencia` (lista serializada en JSON) para registrar de forma
        duradera el tipo de lanzamiento, la ruta/destino, la fuente, la
        ultima comprobacion, la version/producto si existe, la evidencia y
        el nivel de confianza (unidad 3.8.5.1.4.7.6).
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
                    absolute_path, launch_type, confidence, version, producto,
                    evidencia, source, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        c.get("version"),
                        c.get("producto"),
                        c.get("evidencia", "[]") if isinstance(c.get("evidencia"), str)
                        else json.dumps(c.get("evidencia", []), ensure_ascii=False),
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

    def buscar_candidatos_registrados(
        self,
        machine_id: str,
        launch_type: Optional[str] = None,
        fuente: Optional[str] = None,
        limite: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Busca candidatos de aplicacion registrados en `application_candidates`.

        Permite consultar los candidatos que han sido persistidos con su
        registro completo (fuente, ruta/destino, tipo de lanzamiento,
        version/producto, ultima comprobacion, evidencia y nivel de
        confianza, unidad 3.8.5.1.4.7.6).

        Parametros:
        - machine_id: identificador del equipo (aislamiento por equipo).
        - launch_type: filtro opcional por tipo de lanzamiento.
        - fuente: filtro opcional por fuente de descubrimiento.
        - limite: numero maximo de resultados (paginado).
        - offset: desplazamiento para paginacion.

        Retorna:
        Lista de diccionarios con todos los campos de registro de cada
        candidato, incluida `evidencia` deserializada de JSON a lista.
        """
        conn = self.connect()
        condiciones = ["machine_id = ?"]
        parametros: list[object] = [machine_id]
        if launch_type is not None:
            condiciones.append("launch_type = ?")
            parametros.append(launch_type)
        if fuente is not None:
            condiciones.append("source = ?")
            parametros.append(fuente)
        where = " AND ".join(condiciones)
        cur = conn.execute(
            f"""
            SELECT candidate_id, scan_id, machine_id, volume, name,
                   absolute_path, launch_type, confidence AS confianza, version, producto,
                   evidencia, source AS fuente, last_checked_at AS ultima_comprobacion
            FROM application_candidates
            WHERE {where}
            ORDER BY confidence DESC, last_checked_at DESC
            LIMIT ? OFFSET ?
            """,
            (*parametros, limite, offset),
        )
        resultados: list[dict] = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["evidencia"] = json.loads(d.get("evidencia") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["evidencia"] = []
            resultados.append(d)
        return resultados

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

    # ------------------------------------------------------------------ #
    # Volumenes montados en el equipo actual (unidad 3.8.5.1.4.6.6).
    # ------------------------------------------------------------------ #
    def obtener_volumes_montados(self) -> set[str]:
        """
        Devuelve los identificadores de volumen actualmente montados en el
        equipo donde se ejecuta JARVIS.

        Utiliza `psutil.disk_partitions(all=False)` para obtener solo los
        volumenes realmente montados y con medios disponibles (no unidades
        de CD-ROM sin disco, ni recursos de red no conectados).

        En Windows devuelve letras de unidad con dos puntos (ej. {"C:", "D:"}).
        En POSIX devuelve puntos de montaje (ej. {"/", "/mnt/data"}).

        Este metodo no consulta la base de datos: refleja el estado real del
        sistema de archivos en el momento de la llamada.
        """
        montados: set[str] = set()
        try:
            for particion in psutil.disk_partitions(all=False):
                punto = particion.mountpoint or ""
                if not punto:
                    continue
                if os.name == "nt":
                    # Windows: normalizar a "C:" (letra de unidad + dos puntos).
                    # os.path.splitdrive ya incluye los dos puntos en la letra.
                    drive = os.path.splitdrive(punto)[0]
                    if drive:
                        montados.add(drive.upper())
                    else:
                        montados.add(punto.upper())
                else:
                    montados.add(punto)
        except (OSError, PermissionError):
            # Si no se puede enumerar, devolver conjunto vacio: el llamante
            # tratara que no hay volumenes montados y no retornara rutas.
            pass
        return montados

    def search(
        self,
        machine_id: str,
        name: Optional[str] = None,
        ruta: Optional[str] = None,
        extension: Optional[str] = None,
        tipo: Optional[str] = None,
        volume: Optional[str] = None,
        disponible: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "absolute_path",
        solo_volumes_montados: bool = True,
    ) -> list[dict]:
        """
        Busqueda unificada de entradas de inventario por multiples criterios.

        Combina filtros de nombre exacto/normalizado, ruta, extension, tipo,
        volumen y disponibilidad en una sola consulta SQL parametrizada.
        Siempre filtra por machine_id (aislamiento por equipo, 3.8.5.1.4.1.3).
        Cuando `solo_volumes_montados` es True (por defecto), solo devuelve
        entradas de volumenes locales montados en el equipo actual
        (3.8.5.1.4.6.6), evitando devolver rutas de volúmenes no montados.

        Parametros:
        - machine_id: identificador del equipo (obligatorio, aislamiento por equipo).
        - name: nombre exacto o normalizado (comparacion case-insensitive).
        - ruta: prefijo de ruta absoluta (LIKE).
        - extension: extension de archivo (case-insensitive).
        - tipo: tipo de entrada (file, directory, symlink, junction, mount_point, other).
        - volume: volumen donde reside la entrada.
        - disponible: True = no excluida, False = excluida, None = ambas.
        - limit: numero maximo de resultados (paginacion).
        - offset: desplazamiento para paginacion.
        - order_by: campo por el que ordenar (absolute_path por defecto).
        - solo_volumes_montados: si True, filtra para excluir entradas de
          volumenes que no estan montados en el equipo actual.

        Retorna:
        - lista de diccionarios con todos los campos de file_entries.
        """
        conn = self.connect()

        # Construir consulta dinamica con filtros proporcionados.
        where_clauses: list[str] = ["machine_id = ?"]
        params: list[object] = [machine_id]

        if name is not None:
            where_clauses.append("lower(name) = lower(?)")
            params.append(name)
        if ruta is not None:
            where_clauses.append("absolute_path LIKE ?")
            params.append(ruta + "%")
        if extension is not None:
            where_clauses.append("lower(extension) = lower(?)")
            params.append(extension)
        if tipo is not None:
            where_clauses.append("entry_type = ?")
            params.append(tipo)
        if volume is not None:
            where_clauses.append("volume = ?")
            params.append(volume)
        if disponible is not None:
            where_clauses.append("excluded = ?")
            params.append(0 if disponible else 1)

        where_sql = " AND ".join(where_clauses)

        # Validar campo de ordenamiento para evitar inyeccion SQL.
        campos_validos = {
            "absolute_path", "name", "extension", "entry_type", "volume",
            "size_bytes", "modified_at", "created_at", "last_checked_at",
        }
        if order_by not in campos_validos:
            order_by = "absolute_path"

        sql = f"""
            SELECT * FROM file_entries
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cur = conn.execute(sql, params)
        resultados = [dict(r) for r in cur.fetchall()]

        # Filtrar por volumenes montados: evitar devolver rutas de volúmenes
        # que no estan disponibles en el equipo actual (3.8.5.1.4.6.6).
        if solo_volumes_montados:
            volumes_montados = self.obtener_volumes_montados()
            if volumes_montados:
                resultados = [
                    r for r in resultados
                    if self._volumen_de_entrada_esta_montado(r.get("volume", ""), volumes_montados)
                ]

        return resultados

    @staticmethod
    def _volumen_de_entrada_esta_montado(volumen_entrada: str, volumes_montados: set[str]) -> bool:
        """
        Determina si el volumen de una entrada de inventario está montado
        en el equipo actual.

        Normaliza el volumen de la entrada (Windows: letra de unidad con dos
        puntos) y compara contra el conjunto de volumenes montados obtenido
        del sistema operativo real.
        """
        if not volumen_entrada:
            return False
        v = volumen_entrada.strip()
        if os.name == "nt":
            # Windows: normalizar a "C:" (letra de unidad + dos puntos, mayusculas).
            # os.path.splitdrive ya incluye los dos puntos en la letra.
            drive = os.path.splitdrive(v)[0]
            if drive:
                v = drive.upper()
            else:
                v = v.upper()
        return v in volumes_montados

    def count(
        self,
        machine_id: str,
        name: Optional[str] = None,
        ruta: Optional[str] = None,
        extension: Optional[str] = None,
        tipo: Optional[str] = None,
        volume: Optional[str] = None,
        disponible: Optional[bool] = None,
        solo_volumes_montados: bool = True,
    ) -> int:
        """
        Devuelve el total de entradas que coinciden con los mismos filtros que
        `search`, sin cargar filas en memoria.

        Se usa para construir metadatos de paginacion (total de paginas,
        has_more) sin materializar el conjunto completo de resultados.

        Aplica los mismos filtros y aislamiento por `machine_id` que `search`.
        Cuando `solo_volumes_montados` es True (por defecto), solo cuenta
        entradas de volumenes locales montados en el equipo actual
        (3.8.5.1.4.6.6).
        """
        conn = self.connect()

        where_clauses: list[str] = ["machine_id = ?"]
        params: list[object] = [machine_id]

        if name is not None:
            where_clauses.append("lower(name) = lower(?)")
            params.append(name)
        if ruta is not None:
            where_clauses.append("absolute_path LIKE ?")
            params.append(ruta + "%")
        if extension is not None:
            where_clauses.append("lower(extension) = lower(?)")
            params.append(extension)
        if tipo is not None:
            where_clauses.append("entry_type = ?")
            params.append(tipo)
        if volume is not None:
            where_clauses.append("volume = ?")
            params.append(volume)
        if disponible is not None:
            where_clauses.append("excluded = ?")
            params.append(0 if disponible else 1)

        where_sql = " AND ".join(where_clauses)

        if solo_volumes_montados:
            # Para contar solo entradas de volumenes montados, obtenemos
            # entry_id y volumen de cada fila coincidente y filtramos en
            # Python contra el estado real del sistema de archivos.
            cur = conn.execute(
                f"SELECT entry_id, volume FROM file_entries WHERE {where_sql}",
                params,
            )
            rows = cur.fetchall()
            volumes_montados = self.obtener_volumes_montados()
            if not volumes_montados:
                return 0
            return sum(
                1
                for r in rows
                if self._volumen_de_entrada_esta_montado(r["volume"], volumes_montados)
            )

        cur = conn.execute(
            f"SELECT COUNT(*) AS c FROM file_entries WHERE {where_sql}",
            params,
        )
        return int(cur.fetchone()["c"])

    def search_paginated(
        self,
        machine_id: str,
        name: Optional[str] = None,
        ruta: Optional[str] = None,
        extension: Optional[str] = None,
        tipo: Optional[str] = None,
        volume: Optional[str] = None,
        disponible: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "absolute_path",
        cursor: Optional[str] = None,
        solo_volumes_montados: bool = True,
    ) -> dict:
        """
        Busqueda paginada que devuelve resultados junto con metadatos de
        paginacion sin cargar toda la base de datos en memoria.

        Combina `search` (con soporte de cursor y offset) y `count` para
        ofrecer al consumidor:
        - `results`: lista de entradas de la pagina solicitada.
        - `total`: numero total de entradas que coinciden con los filtros.
        - `has_more`: True si hay mas entradas despues de esta pagina.
        - `next_cursor`: entry_id de la ultima entrada devuelta (para
          paginacion por cursor en la siguiente solicitud) o None.
        - `limit`, `offset`, `order_by`: parametros de paginacion usados.

        Cuando `solo_volumes_montados` es True (por defecto), solo devuelve
        entradas de volumenes locales montados en el equipo actual
        (3.8.5.1.4.6.6).

        La paginacion por cursor (`cursor`) es mas eficiente que OFFSET para
        grandes volúmenes porque evita que SQLite examine y descarte filas
        ya recorridas. Cuando se proporciona `cursor`, se usa `entry_id > ?`
        con ORDER BY entry_id, ignorando `offset`.
        """
        results: list[dict]

        if cursor is not None:
            # Paginacion por cursor: mas eficiente que OFFSET en grandes volúmenes.
            conn = self.connect()
            where_clauses: list[str] = [
                "machine_id = ?",
                "entry_id > ?",
            ]
            params: list[object] = [machine_id, cursor]

            if name is not None:
                where_clauses.append("lower(name) = lower(?)")
                params.append(name)
            if ruta is not None:
                where_clauses.append("absolute_path LIKE ?")
                params.append(ruta + "%")
            if extension is not None:
                where_clauses.append("lower(extension) = lower(?)")
                params.append(extension)
            if tipo is not None:
                where_clauses.append("entry_type = ?")
                params.append(tipo)
            if volume is not None:
                where_clauses.append("volume = ?")
                params.append(volume)
            if disponible is not None:
                where_clauses.append("excluded = ?")
                params.append(0 if disponible else 1)

            where_sql = " AND ".join(where_clauses)
            sql = f"""
                SELECT * FROM file_entries
                WHERE {where_sql}
                ORDER BY entry_id
                LIMIT ?
            """
            params.append(limit)
            cur = conn.execute(sql, params)
            results = [dict(r) for r in cur.fetchall()]

            # Filtrar por volumenes montados en la rama de cursor (3.8.5.1.4.6.6).
            if solo_volumes_montados:
                volumes_montados = self.obtener_volumes_montados()
                if volumes_montados:
                    results = [
                        r
                        for r in results
                        if self._volumen_de_entrada_esta_montado(r.get("volume", ""), volumes_montados)
                    ]
                else:
                    results = []

            total = self.count(
                machine_id=machine_id,
                name=name,
                ruta=ruta,
                extension=extension,
                tipo=tipo,
                volume=volume,
                disponible=disponible,
                solo_volumes_montados=solo_volumes_montados,
            )
            next_cursor = results[-1]["entry_id"] if results else None
            # has_more: existen mas entradas despues del cursor con los mismos filtros.
            if next_cursor is not None:
                cur2 = conn.execute(
                    f"SELECT COUNT(*) AS c FROM file_entries WHERE {where_sql} AND entry_id > ?",
                    params[:-1] + [next_cursor],
                )
                has_more = int(cur2.fetchone()["c"]) > 0
            else:
                has_more = False
        else:
            # Primera pagina de recorrido por cursor. Se ordena siempre por
            # entry_id (y no por order_by) para que la cadena de next_cursor
            # sea consistente con las paginas siguientes, que tambien ordenan
            # por entry_id. Ordenar por otro campo haria que el cursor avance
            # sobre un orden distinto y se saltaran o duplicaran entradas.
            conn = self.connect()
            where_clauses: list[str] = ["machine_id = ?"]
            params: list[object] = [machine_id]

            if name is not None:
                where_clauses.append("lower(name) = lower(?)")
                params.append(name)
            if ruta is not None:
                where_clauses.append("absolute_path LIKE ?")
                params.append(ruta + "%")
            if extension is not None:
                where_clauses.append("lower(extension) = lower(?)")
                params.append(extension)
            if tipo is not None:
                where_clauses.append("entry_type = ?")
                params.append(tipo)
            if volume is not None:
                where_clauses.append("volume = ?")
                params.append(volume)
            if disponible is not None:
                where_clauses.append("excluded = ?")
                params.append(0 if disponible else 1)

            where_sql = " AND ".join(where_clauses)
            sql = f"""
                SELECT * FROM file_entries
                WHERE {where_sql}
                ORDER BY entry_id
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            cur = conn.execute(sql, params)
            results = [dict(r) for r in cur.fetchall()]

            # Filtrar por volumenes montados en la primera pagina
            # (3.8.5.1.4.6.6), igual que las paginas cursor posteriores.
            if solo_volumes_montados:
                volumes_montados = self.obtener_volumes_montados()
                if volumes_montados:
                    results = [
                        r for r in results
                        if self._volumen_de_entrada_esta_montado(r.get("volume", ""), volumes_montados)
                    ]
                else:
                    results = []

            total = self.count(
                machine_id=machine_id,
                name=name,
                ruta=ruta,
                extension=extension,
                tipo=tipo,
                volume=volume,
                disponible=disponible,
                solo_volumes_montados=solo_volumes_montados,
            )
            next_cursor = results[-1]["entry_id"] if results else None
            has_more = offset + len(results) < total

        return {
            "results": results,
            "total": total,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "limit": limit,
            "offset": offset if cursor is None else 0,
            "order_by": order_by if cursor is None else "entry_id",
        }

    # ------------------------------------------------------------------ #
    # Busqueda con evidencia de revalidacion real (unidad 3.8.5.1.4.6.3).
    # ------------------------------------------------------------------ #
    def search_con_evidencia(
        self,
        machine_id: str,
        name: Optional[str] = None,
        ruta: Optional[str] = None,
        extension: Optional[str] = None,
        tipo: Optional[str] = None,
        volume: Optional[str] = None,
        disponible: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "absolute_path",
        machine_id_actual: Optional[str] = None,
        solo_volumes_montados: bool = True,
    ) -> dict:
        """
        Busqueda unificada de entradas de inventario con evidencia de
        revalidacion real en el sistema operativo para cada resultado.

        Extiende `search()` anexando a cada entrada los datos de evidencia
        que el consumidor necesita para decidir si revalidar el destino
        antes de usarlo (unidad 3.8.5.1.4.6.3):

        - `procedencia` (source): fuente de descubrimiento de la entrada.
        - `volumen`: volumen donde reside la entrada.
        - `fecha_ultima_comprobacion` (last_checked_at): ultima vez que se
          comprobó la entrada en el inventario.
        - `estado`: tipo de entrada y si esta excluida.
        - `evidencia`: resultado de validar la entrada contra el SO real
          (existencia, tipo, volumen, identidad, accesibilidad).
        - `caducidad`: estado de caducidad (vigente/obsoleto/expirado/desconocido)
          y edad desde la ultima comprobacion.

        Cuando `solo_volumes_montados` es True (por defecto), solo devuelve
        entradas de volumenes locales montados en el equipo actual
        (3.8.5.1.4.6.6).

        La evidencia de validacion se obtiene ejecutando `validar_destino`
        y `esta_caducado` contra el sistema operativo real para cada
        entrada devuelta. Nunca se usa un mock para decidir si una entrada
        necesita revalidacion: la evidencia es siempre observable en el SO.

        Parametros:
        - machine_id: identificador del equipo (obligatorio, aislamiento).
        - name, ruta, extension, tipo, volume, disponible: filtros de busqueda.
        - limit, offset: paginacion (idem `search`).
        - order_by: campo de ordenamiento (idem `search`).
        - machine_id_actual: identificador del equipo actual para la
          comprobacion de identidad. Si None, la identidad se omite.
        - solo_volumes_montados: si True, filtra para excluir entradas de
          volumenes que no estan montados en el equipo actual.

        Retorna:
        - dict con `results`, `total`, `has_more`, `next_cursor`, `limit`,
          `offset`, `order_by` (como `search_paginated`) donde cada entrada
          de `results` incluye ademas los campos de evidencia y caducidad.
        """
        pagina = self.search_paginated(
            machine_id=machine_id,
            name=name,
            ruta=ruta,
            extension=extension,
            tipo=tipo,
            volume=volume,
            disponible=disponible,
            limit=limit,
            offset=offset,
            order_by=order_by,
            solo_volumes_montados=solo_volumes_montados,
        )

        resultados_enriquecidos: list[dict] = []
        for entrada in pagina["results"]:
            enriquecida = dict(entrada)

            # Construir InventoryEntry a partir de los datos de la fila.
            try:
                entry = InventoryEntry(
                    machine_id=entrada.get("machine_id", ""),
                    volume=entrada.get("volume", ""),
                    absolute_path=entrada.get("absolute_path", ""),
                    relative_path=entrada.get("relative_path", ""),
                    name=entrada.get("name", ""),
                    extension=entrada.get("extension", ""),
                    entry_type=EntryType(entrada.get("entry_type", EntryType.OTHER.value)),
                    size_bytes=int(entrada.get("size_bytes", 0)),
                    modified_at=entrada.get("modified_at", "") or "",
                    created_at=entrada.get("created_at", "") or "",
                    accessed_at=entrada.get("accessed_at"),
                    attributes=list(entrada.get("attributes", []) or []),
                    excluded=bool(entrada.get("excluded", False)),
                    exclusion_reason=entrada.get("exclusion_reason"),
                    source=entrada.get("source", "filesystem_scan"),
                    last_checked_at=entrada.get("last_checked_at", "") or "",
                )
            except (ValueError, TypeError, KeyError):
                # Si no se puede reconstruir la entrada, se devuelve sin
                # evidencia de validacion (el consumidor debe revalidar).
                enriquecida["evidencia"] = {
                    "disponible": False,
                    "razon": "No se pudo reconstruir la entrada de inventario para validar.",
                }
                enriquecida["caducidad"] = {
                    "estado": EstadoCaducidad.DESCONOCIDO.value,
                    "edad_segundos": None,
                    "ultimo_check": entrada.get("last_checked_at"),
                    "es_valido_para_uso": False,
                    "razon": "Entrada no reconstruible: caducidad indeterminada.",
                }
                resultados_enriquecidos.append(enriquecida)
                continue

            # Validacion real contra el sistema operativo.
            validacion = validar_destino(entry, machine_id_actual=machine_id_actual)
            enriquecida["evidencia"] = {
                "disponible": True,
                "existencia_ok": validacion.existencia_ok,
                "tipo_ok": validacion.tipo_ok,
                "volumen_ok": validacion.volumen_ok,
                "identidad_ok": validacion.identidad_ok,
                "accesible_ok": validacion.accesible_ok,
                "valido": validacion.valido,
                "errores": validacion.errores,
                "razon": validacion.razon,
            }

            # Caducidad respecto a last_checked_at.
            caducidad = esta_caducado(entry)
            enriquecida["caducidad"] = {
                "estado": caducidad.estado.value,
                "edad_segundos": caducidad.edad_segundos,
                "ultimo_check": caducidad.ultimo_check,
                "es_valido_para_uso": caducidad.es_valido_para_uso,
                "razon": caducidad.razon,
            }

            # Campos planos de conveniencia para el consumidor.
            enriquecida["procedencia"] = entrada.get("source", "filesystem_scan")
            enriquecida["volumen"] = entrada.get("volume")
            enriquecida["fecha_ultima_comprobacion"] = entrada.get("last_checked_at")
            enriquecida["estado"] = {
                "tipo": entrada.get("entry_type"),
                "excluida": bool(entrada.get("excluded", False)),
            }

            resultados_enriquecidos.append(enriquecida)

        pagina["results"] = resultados_enriquecidos
        return pagina

    # ------------------------------------------------------------------ #
    # Diferenciacion de estado de acceso (unidad 3.8.5.1.4.6.4).
    # ------------------------------------------------------------------ #

    # Extensiones de archivo admitidas como lanzamiento de tipo
    # "ejecutable" por el validador de destinos de lanzamiento y el
    # preflight (ApplicationPreflight._is_executable /
    # validate_launch_destination). Se mantiene sincronizada con ese
    # contrato real: solo se considera ejecutable lo que el preflight
    # clasifica como ejecutable lanzable.
    EXTENSIONES_EJECUTABLES: frozenset[str] = frozenset({".exe"})

    def diferenciar_estado_acceso(
        self,
        machine_id: str,
        name: Optional[str] = None,
        ruta: Optional[str] = None,
        extension: Optional[str] = None,
        tipo: Optional[str] = None,
        volume: Optional[str] = None,
        disponible: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "absolute_path",
        machine_id_actual: Optional[str] = None,
        preflight: Optional[ApplicationPreflight] = None,
        solo_volumes_montados: bool = True,
    ) -> dict:
        """
        Busqueda unificada de entradas de inventario con diferenciacion
        de estado de acceso para cada resultado (3.8.5.1.4.6.4).

        Extiende `search_con_evidencia` anexando a cada entrada un bloque
        `diferenciacion` que separa, con evidencia observable del sistema
        operativo real:

        - `encontrado_en_inventario`: la entrada fue devuelta por la
          consulta de inventario (siempre True en los resultados de esta
          busqueda).
        - `existe_ahora`: la ruta existe en el sistema operativo en este
          momento (evidencia de `validar_destino` contra el SO real).
        - `accesible_ahora`: los metadatos de la ruta se pueden leer sin
          error (evidencia de `validar_destino` contra el SO real).
        - `ejecutable`: es un archivo cuyo tipo es FILE y cuya extension
          es admitida como lanzamiento ejecutable (`.exe`, coherente con
          `ApplicationPreflight`).
        - `candidato_a_aplicacion`: es ejecutable, existe, es accesible,
          no esta excluida y pasa la validacion completa de destino.
        - `autorizado_para_lanzamiento`: es candidato a aplicacion y
          pasa la política de preflight real
          (`ApplicationPreflight.check`).

        Cuando `solo_volumes_montados` es True (por defecto), solo devuelve
        entradas de volumenes locales montados en el equipo actual
        (3.8.5.1.4.6.6).

        El preflight solo se consulta cuando la entrada es candidata a
        aplicacion, para no invocar politicas de lanzamiento sobre
        entradas que no pueden lanzarse.

        Los parametros de busqueda son iguales que `search_con_evidencia`,
        además de:
        - preflight: instancia de ApplicationPreflight para la consulta
          de autorizacion. Si se omite, se obtiene la instancia global
          (`get_application_preflight`).

        Retorna el mismo dict paginado que `search_paginated` donde cada
        entrada de `results` incluye el bloque `diferenciacion`.
        """
        if preflight is None:
            preflight = get_application_preflight()

        pagina = self.search_con_evidencia(
            machine_id=machine_id,
            name=name,
            ruta=ruta,
            extension=extension,
            tipo=tipo,
            volume=volume,
            disponible=disponible,
            limit=limit,
            offset=offset,
            order_by=order_by,
            machine_id_actual=machine_id_actual,
            solo_volumes_montados=solo_volumes_montados,
        )

        resultados_diferenciados: list[dict] = []
        for entrada in pagina["results"]:
            diferenciada = dict(entrada)
            diferenciada["diferenciacion"] = self._diferenciar_entrada(
                entrada, preflight
            )
            resultados_diferenciados.append(diferenciada)

        pagina["results"] = resultados_diferenciados
        return pagina

    def _diferenciar_entrada(
        self, entrada: dict, preflight: ApplicationPreflight
    ) -> dict:
        """
        Calcula el bloque `diferenciacion` de una unica entrada de
        inventario.

        Toda la evidencia de existencia, tipo, volumen, identidad y
        accesibilidad proviene de la validacion real contra el sistema
        operativo ya incorporada en `search_con_evidencia`
        (`validar_destino`); aqui no se vuelve a tocar el disco salvo lo
        que el preflight haga internamente para resolver el ejecutable.
        """
        evidencia = entrada.get("evidencia") or {}
        estado = entrada.get("estado") or {}
        extension = str(entrada.get("extension") or "").lower()
        entry_type = entrada.get("entry_type")
        nombre = str(entrada.get("name") or "")
        ruta = str(entrada.get("absolute_path") or "")

        existe_ahora = bool(evidencia.get("existencia_ok"))
        accesible_ahora = bool(evidencia.get("accesible_ok"))
        valido_destino = bool(evidencia.get("valido"))
        excluida = bool(estado.get("excluida"))

        ejecutable = entry_type == EntryType.FILE.value and self._es_extension_ejecutable(
            extension
        )

        candidato_a_aplicacion = (
            ejecutable
            and existe_ahora
            and accesible_ahora
            and not excluida
            and valido_destino
        )

        autorizado_para_lanzamiento = False
        preflight_permitido: Optional[bool] = None
        preflight_motivo: Optional[str] = None

        if candidato_a_aplicacion:
            aplicacion = {
                "name": nombre,
                "app_id": ruta,
                "login_required": None,
                "logged_in": None,
                "resources_available": True,
            }
            resultado_preflight = preflight.check(aplicacion)
            preflight_permitido = bool(
                resultado_preflight.get("allowed", False)
            )
            preflight_motivo = str(resultado_preflight.get("reason", ""))
            autorizado_para_lanzamiento = preflight_permitido

        partes: list[str] = []
        if not existe_ahora:
            partes.append("no existe en el sistema operativo")
        if not accesible_ahora:
            partes.append("no accesible")
        if not ejecutable:
            partes.append("no es ejecutable lanzable")
        if excluida:
            partes.append("excluida del inventario")
        if not valido_destino:
            partes.append("no pasa validacion de destino")
        if candidato_a_aplicacion and not autorizado_para_lanzamiento:
            partes.append(
                f"preflight denegado: {preflight_motivo or 'no permitido'}"
            )

        if autorizado_para_lanzamiento:
            detalle = (
                "Autorizado para lanzamiento: ejecutable existente, "
                "accesible y permitido por preflight."
            )
        elif partes:
            detalle = "No autorizado para lanzamiento: " + "; ".join(partes) + "."
        else:
            detalle = (
                "No es candidato a aplicacion: no cumple condiciones de lanzamiento."
            )

        return {
            "encontrado_en_inventario": True,
            "existe_ahora": existe_ahora,
            "accesible_ahora": accesible_ahora,
            "ejecutable": ejecutable,
            "candidato_a_aplicacion": candidato_a_aplicacion,
            "autorizado_para_lanzamiento": autorizado_para_lanzamiento,
            "detalle": detalle,
            "preflight_permitido": preflight_permitido,
            "preflight_motivo": preflight_motivo,
        }

    @staticmethod
    def _es_extension_ejecutable(extension: Optional[str]) -> bool:
        """True si la extension es una de las admitidas como ejecutable
        lanzable por el contrato real de `ApplicationPreflight`."""
        if not extension:
            return False
        return extension.lower() in SystemInventoryStorage.EXTENSIONES_EJECUTABLES

    # ------------------------------------------------------------------ #
    # Candidatos relevantes para Brain/LLM (unidad 3.8.5.1.4.6.7).
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extraer_palabras_clave_orden(orden: str) -> list[str]:
        """Extrae palabras clave significativas de una orden de usuario.

        Divide la orden en tokens, elimina palabras vacias muy comunes y
        conserva tokens con al menos 2 caracteres que puedan corresponder a
        nombres de aplicaciones, archivos o extensiones. No interpreta
        intencion: solo normaliza el texto para usarlo como criterio de
        busqueda en el inventario.
        """
        if not orden or not isinstance(orden, str):
            return []
        palabras_vacias = {
            "el", "la", "los", "las", "un", "una", "unos", "unas",
            "de", "del", "en", "a", "al", "por", "para", "con", "sin",
            "sobre", "entre", "hasta", "desde", "y", "o", "pero", "si",
            "que", "como", "cuando", "donde", "quien", "cual", "cuales",
            "abre", "abrir", "lanzar", "ejecutar", "buscar", "busca",
            "encuentra", "encuentre", "muestra", "mostrar", "listar",
            "lista", "orden", "comando", "ejecuta", "inicia", "iniciar",
            "run", "open", "close", "start", "stop", "find", "search",
            "the", "a", "an", "of", "in", "to", "for", "with", "from",
            "by", "at", "on", "as", "is", "it", "be", "or", "and", "jarvis",
        }
        tokens: list[str] = []
        for token in orden.split():
            token_limpio = token.strip(".,;:!?()[]{}\"'").lower()
            if len(token_limpio) >= 2 and token_limpio not in palabras_vacias:
                tokens.append(token_limpio)
        # Eliminar duplicados preservando orden.
        vistos: set[str] = set()
        resultado: list[str] = []
        for t in tokens:
            if t not in vistos:
                vistos.add(t)
                resultado.append(t)
        return resultado

    @staticmethod
    def _es_ruta_privada(ruta: str) -> bool:
        """True si la ruta parece ser una ruta privada/usuario que no debe
        exponerse completa en el contexto conversacional.

        Se trata como privada cualquier ruta que contenga segmentos de
        perfil de usuario (Users/<nombre>), datos de aplicacion locales
        (AppData), o carpetas de usuario estandar (Documentos, Descargas,
        Desktop, etc.) cuando el nombre del usuario es detectable.
        """
        if not ruta:
            return False
        r = ruta.replace("\\", "/")
        segmentos_privados = {
            "appdata", "local", "locallow", "roaming",
            "users", "documentos", "downloads", "desktop",
            "document", "download", "onedrive", "dropbox",
        }
        partes = [p.lower() for p in r.split("/") if p]
        return any(p in segmentos_privados for p in partes)

    @staticmethod
    def _resumir_ruta_para_contexto(ruta: str, es_privada: bool) -> str:
        """Devuelve una version de la ruta segura para el contexto conversacional.

        Si la ruta es privada, devuelve solo el nombre del archivo y el volumen,
        sin la ruta completa. Si no es privada, devuelve la ruta completa
        normalizada (el contexto ya esta limitado a candidatos relevantes).
        """
        if not ruta:
            return ""
        if es_privada:
            # Solo volumen + nombre de archivo, sin directorios intermedios.
            nombre = Path(ruta).name
            drive = os.path.splitdrive(ruta.replace("\\", "/"))[0]
            if drive:
                return f"{drive}/{nombre}"
            return nombre
        return ruta

    def _buscar_nombre_parcial(
        self,
        machine_id: str,
        palabra: str,
        limit: int,
        solo_volumes_montados: bool = True,
    ) -> list[dict]:
        """Busqueda parcial (LIKE) sobre el nombre de entrada.

        Se usa como fallback cuando la coincidencia exacta de `search` no
        devuelve resultados (ej. buscar "chrome" no coincide con
        name="chrome.exe"). Hace una consulta directa con LIKE sobre el
        campo name, aplicando aislamiento por machine_id y filtro de
        volumenes montados si procede.
        """
        conn = self.connect()
        where_clauses: list[str] = ["machine_id = ?", "lower(name) LIKE lower(?)"]
        params: list[object] = [machine_id, f"%{palabra}%"]
        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT * FROM file_entries
            WHERE {where_sql}
            ORDER BY absolute_path
            LIMIT ? OFFSET 0
        """
        params.extend([limit])
        cur = conn.execute(sql, params)
        resultados = [dict(r) for r in cur.fetchall()]

        # Filtrar por volumenes montados si procede.
        if solo_volumes_montados:
            volumes_montados = self.obtener_volumes_montados()
            if volumes_montados:
                resultados = [
                    r for r in resultados
                    if self._volumen_de_entrada_esta_montado(r.get("volume", ""), volumes_montados)
                ]

        return resultados

    def buscar_candidatos_para_orden(
        self,
        machine_id: str,
        orden: str,
        limit: int = 10,
        machine_id_actual: Optional[str] = None,
        solo_volumes_montados: bool = True,
    ) -> dict:
        """Busca candidatos de inventario relevantes para una orden de usuario.

        Unidad 3.8.5.1.4.6.7: limitar los datos enviados a Brain/LLM a los
        candidatos relevantes para la orden, sin introducir el inventario
        completo ni rutas privadas en el contexto conversacional.

        El metodo extrae palabras clave de la orden y las usa como filtros
        de busqueda (nombre y extension), de modo que solo se devuelven
        candidatos que puedan estar relacionados con la orden. Cada resultado
        incluye un resumen limitado de campos y una ruta segura para el
        contexto conversacional (rutas privadas se resumen a volumen +
        nombre de archivo).

        Parametros:
        - machine_id: identificador del equipo (aislamiento por equipo).
        - orden: texto de la orden del usuario (ej. "abre chrome",
          "busca el archivo reporte").
        - limit: numero maximo de candidatos a devolver.
        - machine_id_actual: identificador del equipo actual para comprobacion
          de identidad en la evidencia.
        - solo_volumes_montados: si True, solo devuelve entradas de volumenes
          montados en el equipo actual.

        Retorna:
        - dict con:
          - `orden_original`: la orden recibida.
          - `palabras_clave`: palabras clave extraidas para la busqueda.
          - `total_candidatos_inventario`: total de entradas en el inventario
            del equipo (para comparar con lo devuelto; demuestra limitacion).
          - `total_devuelto`: numero de candidatos devueltos.
          - `limit`: limite aplicado.
          - `resultados`: lista de diccionarios con campos limitados:
            `name`, `extension`, `entry_type`, `volume`, `ruta_contexto`,
            `evidencia` (resumen de validacion real), `candidato_a_aplicacion`,
            `es_ruta_privada`.
          - `filtro_aplicado`: descripcion del filtro usado.
        """
        if not machine_id:
            raise ValueError("machine_id es obligatorio.")

        palabras_clave = self._extraer_palabras_clave_orden(orden)

        # Total de entradas en el inventario para este equipo (antes de filtrar).
        try:
            total_inventario = self.count(machine_id, solo_volumes_montados=solo_volumes_montados)
        except Exception:
            total_inventario = 0

        resultados: list[dict] = []

        if palabras_clave:
            # Buscar por cada palabra clave. Primero coincidencia exacta de
            # nombre y extension mediante la API `search`; si no hay
            # resultados, hacer busqueda parcial (LIKE) sobre el nombre.
            entry_ids_vistos: set[str] = set()
            for palabra in palabras_clave:
                # Busqueda por nombre exacto y por extension.
                por_nombre = self.search(
                    machine_id=machine_id,
                    name=palabra,
                    limit=limit,
                    solo_volumes_montados=solo_volumes_montados,
                )
                por_extension: list[dict] = []
                if palabra.startswith(".") or len(palabra) <= 5:
                    por_extension = self.search(
                        machine_id=machine_id,
                        extension=palabra,
                        limit=limit,
                        solo_volumes_montados=solo_volumes_montados,
                    )
                candidatos = list({e.get("entry_id"): e for e in por_nombre + por_extension if e.get("entry_id")}.values())
                # Fallback: busqueda parcial (LIKE) sobre el nombre si la
                # exacta no devolvio nada para esta palabra clave.
                if not candidatos:
                    candidatos = self._buscar_nombre_parcial(
                        machine_id, palabra, limit,
                        solo_volumes_montados=solo_volumes_montados,
                    )
                for entrada in candidatos:
                    eid = entrada.get("entry_id")
                    if eid in entry_ids_vistos:
                        continue
                    entry_ids_vistos.add(eid)
                    if len(resultados) >= limit:
                        break
                    resultados.append(self._formato_candidato_contexto(
                        entrada, machine_id_actual=machine_id_actual
                    ))
                if len(resultados) >= limit:
                    break
        else:
            # Sin palabras clave: no devolver el inventario completo.
            # Devolver una lista vacia con indicacion de que no hay filtro.
            pass

        # Ordenar: primero ejecutables/candidatos a aplicacion, luego por nombre.
        resultados.sort(
            key=lambda r: (
                not r.get("candidato_a_aplicacion", False),
                str(r.get("name", "")),
            )
        )

        return {
            "orden_original": orden,
            "palabras_clave": palabras_clave,
            "total_candidatos_inventario": total_inventario,
            "total_devuelto": len(resultados),
            "limit": limit,
            "resultados": resultados,
            "filtro_aplicado": "palabras_clave_orden" if palabras_clave else "sin_palabras_clave",
        }

    def _formato_candidato_contexto(
        self, entrada: dict, machine_id_actual: Optional[str] = None
    ) -> dict:
        """Formatea una entrada de inventario para el contexto conversacional.

        Incluye solo campos esenciales y una ruta segura (rutas privadas se
        resumen). Ademas incluye un resumen de evidencia de validacion real
        cuando este disponible.
        """
        ruta = str(entrada.get("absolute_path") or "")
        es_privada = self._es_ruta_privada(ruta)
        nombre = str(entrada.get("name") or "")
        extension = str(entrada.get("extension") or "")
        entry_type = entrada.get("entry_type")
        volumen = entrada.get("volume")
        excluida = bool(entrada.get("excluded", False))

        # Resumen de evidencia real si esta disponible.
        evidencia = entrada.get("evidencia") or {}
        evid_resumen = {
            "disponible": bool(evidencia.get("disponible")),
            "existencia_ok": bool(evidencia.get("existencia_ok")),
            "valido": bool(evidencia.get("valido")),
            "razon": str(evidencia.get("razon") or ""),
        }

        # Diferenciacion si esta disponible.
        diff = entrada.get("diferenciacion") or {}
        candidato_app = bool(diff.get("candidato_a_aplicacion"))
        autorizado = bool(diff.get("autorizado_para_lanzamiento"))

        return {
            "name": nombre,
            "extension": extension,
            "entry_type": entry_type,
            "volume": volumen,
            "ruta_contexto": self._resumir_ruta_para_contexto(ruta, es_privada),
            "es_ruta_privada": es_privada,
            "excluida": excluida,
            "evidencia": evid_resumen,
            "candidato_a_aplicacion": candidato_app,
            "autorizado_para_lanzamiento": autorizado,
        }

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
