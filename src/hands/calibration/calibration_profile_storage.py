"""
Persistencia local de perfiles de calibracion UI (SQLite por equipo y topologia).

Cubre (referencia de localizacion en el roadmap): 3.8.6.8.2 - 3.8.6.8.5.

Que guarda y donde:

* Tablas ``calibration_profiles`` y ``calibration_controls`` de
  ``data/system_inventory.sqlite3`` (esquema v6, creadas por la migracion
  versionada y transaccional de ``SystemInventoryStorage``). No existe ninguna
  otra copia: nunca se escribe en ``data/memory/entities.json``,
  ``data/knowledge/entities.json`` ni en ``data/macros_coords.json``.
* Clave de calibracion: ``machine_id`` + ID estable de aplicacion
  (``app_id``) + ID logico del control (``control_id``) + huella de
  ventana/monitor/escala (``window_fingerprint``).
* Geometria persistida relativa al area cliente: ``client_box_normalized``
  (CLIENT_NORMALIZED, 0..1) y, opcionalmente, ``client_box_px``
  (WINDOW_CLIENT). Las coordenadas absolutas del escritorio solo existen en
  ``absolute_cache`` del perfil, como cache invalidable.
* Estados separados por control: ``semantic_state``, ``geometric_state`` y
  ``action_state`` (``CalibrationState``). Un solo modelo con confianza alta
  no basta para ``VALIDADO`` (ver ``check_control_record``).
* Un perfil se activa solo si su estado es ``VALIDADO``. Un perfil fallido
  (cualquier otro estado) se conserva como evidencia inactiva y nunca
  sustituye al ultimo ``VALIDADO`` de la misma huella.
* Aislamiento estricto: toda lectura y escritura filtra por el ``machine_id``
  del almacen. Si la base pertenece a otro equipo (``InventoryIncompatibleMachineError``)
  o esta corrupta y no se pudo recuperar (``InventoryCorruptError``), el
  almacen queda bloqueado: las lecturas devuelven vacio y las escrituras
  levantan ``CalibrationStoreBlocked``. Nunca se sobrescribe una base
  corrupta ni se reutilizan datos de otro equipo.
* No se guardan capturas de pantalla.

Uso:

    store = CalibrationProfileStore()
    store.initialize()
    store.save_profile(perfil)               # transaccion atomica
    activo = store.get_active_profile("app_chrome", window_fingerprint=fp)
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.core.log import get_logger

logger = get_logger(__name__)


# ============================================================================
# ESTADOS Y CONSTANTES
# ============================================================================


class CalibrationState(str, Enum):
    """Estado de una dimension (semantica, geometrica o de accion) o de un perfil."""

    PENDIENTE = "PENDIENTE"
    CANDIDATO = "CANDIDATO"
    DETECTADO = "DETECTADO"
    VALIDADO = "VALIDADO"
    OBSOLETO = "OBSOLETO"
    NO_VERIFICADO = "NO_VERIFICADO"
    BLOQUEADO = "BLOQUEADO"


# Metodos de interaccion admitidos para un control.
INTERACTION_METHODS = frozenset({"accessibility_action", "pointer", "keyboard", "none"})

# Procedencias que se consideran geometria aportada por el propio SO
# (arbol de accesibilidad). Basta por si sola para validar la geometria.
ACCESSIBILITY_PROVENANCE = frozenset({"accessibility", "uia", "ax"})

# Numero minimo de fuentes independientes (no accesibilidad) para validar la
# geometria de un control: un solo modelo no basta (3.8.6.8.3).
MIN_INDEPENDENT_VISUAL_SOURCES = 2

# Perfiles fallidos/inactivos que se conservan por aplicacion como evidencia.
MAX_INACTIVE_PROFILES_PER_APP = 5

# Claves de metadata que nunca deben llegar a la base (privacidad).
_FORBIDDEN_METADATA_KEYS = frozenset({"screenshot", "image", "frame", "capture_path", "title"})


class CalibrationStoreError(RuntimeError):
    """Error de contrato al guardar o leer perfiles de calibracion."""


class CalibrationStoreBlocked(CalibrationStoreError):
    """El almacen no puede usarse (base de otro equipo o corrupta sin recuperar)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _as_state(value: Any, default: CalibrationState = CalibrationState.PENDIENTE) -> CalibrationState:
    if isinstance(value, CalibrationState):
        return value
    try:
        return CalibrationState(str(value).upper())
    except ValueError:
        return default


def _tuple_or_none(value: Any, length: int, cast: Any = float) -> Optional[Tuple[Any, ...]]:
    if value is None:
        return None
    try:
        items = tuple(cast(v) for v in value)
    except (TypeError, ValueError):
        return None
    if len(items) != length:
        return None
    return items


def default_db_path() -> Path:
    """Ruta absoluta de ``data/system_inventory.sqlite3`` en la raiz del proyecto.

    Se usa la ruta absoluta (la misma que usa el preflight) para no crear una
    segunda base si JARVIS se arranca fuera de su carpeta.
    """
    from src.core.config import get_project_root

    return Path(get_project_root()) / "data" / "system_inventory.sqlite3"


# ============================================================================
# MODELOS
# ============================================================================


@dataclass
class CalibratedControlRecord:
    """Control calibrado con geometria relativa al area cliente.

    ``client_box_normalized`` es (left, top, right, bottom) en 0..1 respecto
    al area cliente (CLIENT_NORMALIZED). ``client_box_px`` es la misma caja en
    pixeles/puntos del area cliente (WINDOW_CLIENT) en el momento de calibrar.
    ``confidences`` guarda una confianza por dimension
    (``detection``, ``semantic``, ``interactivity``, ``geometry``...), nunca
    una sola puntuacion agregada.
    """

    control_id: str
    app_id: str
    name: str = ""
    control_type: str = "element"
    semantic_state: CalibrationState = CalibrationState.PENDIENTE
    geometric_state: CalibrationState = CalibrationState.PENDIENTE
    action_state: CalibrationState = CalibrationState.PENDIENTE
    client_box_normalized: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    client_box_px: Optional[Tuple[int, int, int, int]] = None
    safe_point_normalized: Optional[Tuple[float, float]] = None
    interaction_method: str = "none"
    provenance: List[str] = field(default_factory=list)
    detector_versions: Dict[str, str] = field(default_factory=dict)
    original_box: Optional[Tuple[float, float, float, float]] = None
    refined_box: Optional[Tuple[float, float, float, float]] = None
    confidences: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.semantic_state = _as_state(self.semantic_state)
        self.geometric_state = _as_state(self.geometric_state)
        self.action_state = _as_state(self.action_state)
        box = _tuple_or_none(self.client_box_normalized, 4, float)
        self.client_box_normalized = box if box is not None else (0.0, 0.0, 0.0, 0.0)  # type: ignore[assignment]
        self.client_box_px = _tuple_or_none(self.client_box_px, 4, int)  # type: ignore[assignment]
        self.safe_point_normalized = _tuple_or_none(self.safe_point_normalized, 2, float)  # type: ignore[assignment]
        self.original_box = _tuple_or_none(self.original_box, 4, float)  # type: ignore[assignment]
        self.refined_box = _tuple_or_none(self.refined_box, 4, float)  # type: ignore[assignment]
        self.provenance = [str(p) for p in (self.provenance or [])]
        self.detector_versions = {str(k): str(v) for k, v in (self.detector_versions or {}).items()}
        self.confidences = {str(k): float(v) for k, v in (self.confidences or {}).items()}
        self.reasons = [str(r) for r in (self.reasons or [])]

    @property
    def resource_id(self) -> str:
        return "%s.%s" % (self.app_id, self.control_id)

    def normalized_center(self) -> Tuple[float, float]:
        if self.safe_point_normalized is not None:
            return (float(self.safe_point_normalized[0]), float(self.safe_point_normalized[1]))
        left, top, right, bottom = self.client_box_normalized
        return ((left + right) / 2.0, (top + bottom) / 2.0)

    def is_actionable(self) -> bool:
        """True si el control tiene una accion real validada y utilizable."""
        if self.action_state != CalibrationState.VALIDADO:
            return False
        if self.interaction_method not in INTERACTION_METHODS or self.interaction_method == "none":
            return False
        if self.interaction_method == "pointer":
            return self.geometric_state == CalibrationState.VALIDADO
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "app_id": self.app_id,
            "name": self.name,
            "control_type": self.control_type,
            "semantic_state": self.semantic_state.value,
            "geometric_state": self.geometric_state.value,
            "action_state": self.action_state.value,
            "client_box_normalized": list(self.client_box_normalized),
            "client_box_px": list(self.client_box_px) if self.client_box_px else None,
            "safe_point_normalized": list(self.safe_point_normalized) if self.safe_point_normalized else None,
            "interaction_method": self.interaction_method,
            "provenance": list(self.provenance),
            "detector_versions": dict(self.detector_versions),
            "original_box": list(self.original_box) if self.original_box else None,
            "refined_box": list(self.refined_box) if self.refined_box else None,
            "confidences": dict(self.confidences),
            "reasons": list(self.reasons),
        }


@dataclass
class CalibrationProfile:
    """Perfil de calibracion de una aplicacion en un equipo y entorno concretos."""

    profile_id: str
    machine_id: str
    app_id: str
    topology_fingerprint: str = ""
    window_fingerprint: str = ""
    display_id: str = ""
    scale_factor: Optional[float] = None
    dpi: Optional[int] = None
    display_pixel_size: Optional[Tuple[int, int]] = None
    orientation: str = ""
    window_state: str = ""
    client_size: Optional[Tuple[int, int]] = None
    platform: str = ""
    status: CalibrationState = CalibrationState.PENDIENTE
    created_at: str = ""
    updated_at: str = ""
    controls: List[CalibratedControlRecord] = field(default_factory=list)
    absolute_cache: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = False
    obsolete_reason: Optional[str] = None

    def __post_init__(self) -> None:
        self.status = _as_state(self.status)
        self.display_pixel_size = _tuple_or_none(self.display_pixel_size, 2, int)  # type: ignore[assignment]
        self.client_size = _tuple_or_none(self.client_size, 2, int)  # type: ignore[assignment]
        self.controls = list(self.controls or [])
        self.absolute_cache = dict(self.absolute_cache or {})
        self.metadata = dict(self.metadata or {})

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def get_control(self, control_id: str) -> Optional[CalibratedControlRecord]:
        for control in self.controls:
            if control.control_id == control_id:
                return control
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "machine_id": self.machine_id,
            "app_id": self.app_id,
            "topology_fingerprint": self.topology_fingerprint,
            "window_fingerprint": self.window_fingerprint,
            "display_id": self.display_id,
            "scale_factor": self.scale_factor,
            "dpi": self.dpi,
            "display_pixel_size": list(self.display_pixel_size) if self.display_pixel_size else None,
            "orientation": self.orientation,
            "window_state": self.window_state,
            "client_size": list(self.client_size) if self.client_size else None,
            "platform": self.platform,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active,
            "obsolete_reason": self.obsolete_reason,
            "controls": [c.to_dict() for c in self.controls],
            "absolute_cache": dict(self.absolute_cache),
            "metadata": dict(self.metadata),
        }


# ============================================================================
# VALIDACION DE CONTRATO
# ============================================================================


def _valid_normalized_box(box: Sequence[float]) -> bool:
    try:
        left, top, right, bottom = [float(v) for v in box]
    except (TypeError, ValueError):
        return False
    values = (left, top, right, bottom)
    if any(math.isnan(v) or math.isinf(v) for v in values):
        return False
    if not all(0.0 <= v <= 1.0 for v in values):
        return False
    return right > left and bottom > top


def check_control_record(record: CalibratedControlRecord) -> List[str]:
    """Devuelve los problemas de contrato de un control (lista vacia = valido).

    Reglas:
    * ``control_id`` y ``app_id`` no vacios.
    * ``client_box_normalized`` dentro de 0..1 y no degenerada (solo se
      persiste geometria que paso las puertas de calidad).
    * ``safe_point_normalized`` (si existe) dentro de la caja normalizada.
    * ``interaction_method`` en ``INTERACTION_METHODS``.
    * ``geometric_state == VALIDADO`` exige procedencia de accesibilidad del
      SO o al menos ``MIN_INDEPENDENT_VISUAL_SOURCES`` fuentes distintas:
      un solo modelo con confianza alta no basta.
    * ``action_state == VALIDADO`` exige un metodo de interaccion real
      (distinto de ``none``) y, si es ``pointer``, geometria VALIDADA.
    * ``semantic_state == VALIDADO`` exige al menos una procedencia.
    """
    problems: List[str] = []
    if not str(record.control_id or "").strip():
        problems.append("control_id vacio")
    if not str(record.app_id or "").strip():
        problems.append("app_id vacio")
    if not _valid_normalized_box(record.client_box_normalized):
        problems.append("client_box_normalized fuera de 0..1 o degenerada")
    if record.safe_point_normalized is not None:
        sx, sy = record.safe_point_normalized
        left, top, right, bottom = record.client_box_normalized
        if not (left <= sx <= right and top <= sy <= bottom):
            problems.append("safe_point_normalized fuera de la caja del control")
    if record.interaction_method not in INTERACTION_METHODS:
        problems.append("interaction_method desconocido: %s" % record.interaction_method)
    sources = {p.strip().lower() for p in record.provenance if p and p.strip()}
    if record.geometric_state == CalibrationState.VALIDADO:
        has_accessibility = bool(sources & ACCESSIBILITY_PROVENANCE)
        visual_sources = sources - ACCESSIBILITY_PROVENANCE
        if not has_accessibility and len(visual_sources) < MIN_INDEPENDENT_VISUAL_SOURCES:
            problems.append(
                "geometria VALIDADO con una sola fuente visual (%s): un solo modelo no basta"
                % (sorted(visual_sources) or "ninguna")
            )
    if record.action_state == CalibrationState.VALIDADO:
        if record.interaction_method == "none":
            problems.append("accion VALIDADO sin metodo de interaccion real")
        if record.interaction_method == "pointer" and record.geometric_state != CalibrationState.VALIDADO:
            problems.append("accion por puntero VALIDADO sin geometria VALIDADO")
    if record.semantic_state == CalibrationState.VALIDADO and not sources:
        problems.append("semantica VALIDADO sin procedencia")
    return problems


def check_profile(profile: CalibrationProfile) -> List[str]:
    """Problemas de contrato de un perfil completo (lista vacia = valido)."""
    problems: List[str] = []
    if not str(profile.app_id or "").strip():
        problems.append("app_id vacio")
    if not str(profile.machine_id or "").strip():
        problems.append("machine_id vacio")
    seen = set()
    for control in profile.controls:
        if control.app_id != profile.app_id:
            problems.append("control %s pertenece a otra aplicacion" % control.control_id)
        if control.control_id in seen:
            problems.append("control_id duplicado: %s" % control.control_id)
        seen.add(control.control_id)
        for problem in check_control_record(control):
            problems.append("%s: %s" % (control.control_id, problem))
    if profile.status == CalibrationState.VALIDADO:
        if not profile.controls:
            problems.append("perfil VALIDADO sin controles")
        if not profile.window_fingerprint:
            problems.append("perfil VALIDADO sin window_fingerprint")
        if not profile.client_size:
            problems.append("perfil VALIDADO sin client_size")
        if profile.scale_factor is None:
            problems.append("perfil VALIDADO sin scale_factor")
    for key in profile.metadata:
        if str(key).lower() in _FORBIDDEN_METADATA_KEYS:
            problems.append("metadata contiene clave no permitida: %s" % key)
    return problems


# ============================================================================
# ALMACEN
# ============================================================================


class CalibrationProfileStore:
    """Almacen SQLite local de perfiles de calibracion, aislado por ``machine_id``.

    Argumentos:
        db_path: ruta de la base (por defecto ``default_db_path()``).
        machine_id: identificador del equipo (por defecto ``generate_machine_id()``).
        allow_foreign_machine_db: si True, una base cuyo inventario pertenece a
            otro equipo se usa igualmente, siempre filtrando por el
            ``machine_id`` propio (decision explicita; por defecto False =
            almacen bloqueado).
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        machine_id: Optional[str] = None,
        allow_foreign_machine_db: bool = False,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        if machine_id is None:
            from src.hands.inventory.system_inventory import generate_machine_id

            machine_id = generate_machine_id()
        self.machine_id = str(machine_id)
        self.allow_foreign_machine_db = bool(allow_foreign_machine_db)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._initialized = False
        self.blocked_reason: Optional[str] = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None

    def initialize(self) -> bool:
        """Aplica el esquema/migraciones del inventario y abre la conexion propia.

        Devuelve True si el almacen queda utilizable. Si la base pertenece a
        otro equipo o esta corrupta sin copia valida, queda bloqueado
        (``blocked_reason``) y devuelve False sin tocar los datos.
        """
        with self._lock:
            if self._initialized:
                return not self.is_blocked
            from src.hands.inventory.system_inventory_storage import (
                InventoryCorruptError,
                InventoryIncompatibleMachineError,
                SystemInventoryStorage,
            )

            storage = SystemInventoryStorage(self.db_path)
            try:
                version = storage.initialize(
                    machine_id_actual=self.machine_id,
                    permitir_otro_equipo=self.allow_foreign_machine_db,
                )
                if not self._has_calibration_tables(storage):
                    self.blocked_reason = (
                        "esquema del inventario v%s sin tablas de calibracion compatibles" % version
                    )
            except InventoryIncompatibleMachineError as exc:
                self.blocked_reason = "base de otro equipo: %s" % exc
            except InventoryCorruptError as exc:
                self.blocked_reason = "base corrupta sin copia valida: %s" % exc
            except sqlite3.DatabaseError as exc:
                self.blocked_reason = "base ilegible: %s" % exc
            finally:
                try:
                    storage.close()
                except Exception as exc:  # pragma: no cover - cierre defensivo
                    logger.debug("Cierre de SystemInventoryStorage: %s", exc)
            self._initialized = True
            if self.is_blocked:
                logger.warning("Almacen de calibracion bloqueado: %s", self.blocked_reason)
                return False
            self._connect()
            return True

    @staticmethod
    def _has_calibration_tables(storage: Any) -> bool:
        try:
            conn = storage.connect()
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                "('calibration_profiles','calibration_controls')"
            ).fetchall()
            return len(rows) == 2
        except sqlite3.DatabaseError:
            return False

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            # Conexion propia en modo autocommit: las transacciones se abren y
            # cierran explicitamente (BEGIN IMMEDIATE / COMMIT / ROLLBACK).
            conn = sqlite3.connect(str(self.db_path), isolation_level=None, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None
            self._initialized = False

    def _ensure_ready(self, for_write: bool) -> Optional[sqlite3.Connection]:
        if not self._initialized:
            self.initialize()
        if self.is_blocked:
            if for_write:
                raise CalibrationStoreBlocked(self.blocked_reason or "almacen bloqueado")
            return None
        return self._connect()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def save_profile(self, profile: CalibrationProfile) -> str:
        """Guarda un perfil en una unica transaccion y devuelve su ``profile_id``.

        * El perfil debe pertenecer a este ``machine_id``.
        * ``check_profile`` debe pasar: si no, se levanta
          ``CalibrationStoreError`` sin escribir nada.
        * Si ``status == VALIDADO`` el perfil pasa a ser el activo de su
          (aplicacion, huella de ventana) y el anterior activo deja de serlo.
        * Si no es VALIDADO se guarda inactivo como evidencia; el ultimo
          VALIDADO sigue activo.
        * Ante cualquier error se hace rollback completo.
        """
        with self._lock:
            conn = self._ensure_ready(for_write=True)
            assert conn is not None
            if not profile.machine_id:
                profile.machine_id = self.machine_id
            if profile.machine_id != self.machine_id:
                raise CalibrationStoreError(
                    "El perfil pertenece a otro equipo; no se guarda en este almacen"
                )
            problems = check_profile(profile)
            if problems:
                raise CalibrationStoreError("Perfil de calibracion invalido: %s" % "; ".join(problems))
            if not profile.profile_id:
                profile.profile_id = CalibrationProfile.new_id()
            now = _now_iso()
            if not profile.created_at:
                profile.created_at = now
            profile.updated_at = now
            activate = profile.status == CalibrationState.VALIDADO
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR IGNORE INTO machines(machine_id, created_at) VALUES (?, ?)",
                    (self.machine_id, now),
                )
                if activate:
                    conn.execute(
                        "UPDATE calibration_profiles SET is_active = 0, updated_at = ? "
                        "WHERE machine_id = ? AND app_id = ? AND window_fingerprint = ? "
                        "AND is_active = 1 AND profile_id != ?",
                        (now, self.machine_id, profile.app_id, profile.window_fingerprint, profile.profile_id),
                    )
                self._upsert_profile_row(conn, profile, activate)
                self._replace_controls(conn, profile)
                self._prune_inactive(conn, profile.app_id)
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error as rb_exc:
                    logger.warning("Rollback de perfil de calibracion fallo: %s", rb_exc)
                raise
            profile.is_active = activate
            logger.info(
                "Perfil de calibracion guardado app=%s estado=%s activo=%s controles=%d",
                profile.app_id,
                profile.status.value,
                activate,
                len(profile.controls),
            )
            return profile.profile_id

    def _upsert_profile_row(self, conn: sqlite3.Connection, profile: CalibrationProfile, activate: bool) -> None:
        dps = profile.display_pixel_size or (None, None)
        cs = profile.client_size or (None, None)
        conn.execute(
            """
            INSERT INTO calibration_profiles (
                profile_id, machine_id, app_id, platform, topology_fingerprint,
                window_fingerprint, display_id, scale_factor, dpi,
                display_pixel_width, display_pixel_height, orientation,
                window_state, client_width, client_height, status, is_active,
                absolute_cache, metadata, obsolete_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                platform = excluded.platform,
                topology_fingerprint = excluded.topology_fingerprint,
                window_fingerprint = excluded.window_fingerprint,
                display_id = excluded.display_id,
                scale_factor = excluded.scale_factor,
                dpi = excluded.dpi,
                display_pixel_width = excluded.display_pixel_width,
                display_pixel_height = excluded.display_pixel_height,
                orientation = excluded.orientation,
                window_state = excluded.window_state,
                client_width = excluded.client_width,
                client_height = excluded.client_height,
                status = excluded.status,
                is_active = excluded.is_active,
                absolute_cache = excluded.absolute_cache,
                metadata = excluded.metadata,
                obsolete_reason = excluded.obsolete_reason,
                updated_at = excluded.updated_at
            WHERE calibration_profiles.machine_id = excluded.machine_id
            """,
            (
                profile.profile_id,
                self.machine_id,
                profile.app_id,
                profile.platform or "",
                profile.topology_fingerprint or "",
                profile.window_fingerprint or "",
                profile.display_id or "",
                profile.scale_factor,
                profile.dpi,
                dps[0],
                dps[1],
                profile.orientation or "",
                profile.window_state or "",
                cs[0],
                cs[1],
                profile.status.value,
                1 if activate else 0,
                _json_dumps(profile.absolute_cache),
                _json_dumps(profile.metadata),
                profile.obsolete_reason,
                profile.created_at,
                profile.updated_at,
            ),
        )
        row = conn.execute(
            "SELECT machine_id FROM calibration_profiles WHERE profile_id = ?",
            (profile.profile_id,),
        ).fetchone()
        if row is None or row["machine_id"] != self.machine_id:
            raise CalibrationStoreError("profile_id ya usado por otro equipo")

    def _replace_controls(self, conn: sqlite3.Connection, profile: CalibrationProfile) -> None:
        conn.execute(
            "DELETE FROM calibration_controls WHERE profile_id = ? AND machine_id = ?",
            (profile.profile_id, self.machine_id),
        )
        for control in profile.controls:
            conn.execute(
                """
                INSERT INTO calibration_controls (
                    profile_id, control_id, machine_id, app_id, name, control_type,
                    semantic_state, geometric_state, action_state,
                    client_box_normalized, client_box_px, safe_point_normalized,
                    interaction_method, provenance, detector_versions,
                    original_box, refined_box, confidences, reasons
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    control.control_id,
                    self.machine_id,
                    profile.app_id,
                    control.name or "",
                    control.control_type or "element",
                    control.semantic_state.value,
                    control.geometric_state.value,
                    control.action_state.value,
                    _json_dumps(list(control.client_box_normalized)),
                    _json_dumps(list(control.client_box_px)) if control.client_box_px else None,
                    _json_dumps(list(control.safe_point_normalized)) if control.safe_point_normalized else None,
                    control.interaction_method,
                    _json_dumps(control.provenance),
                    _json_dumps(control.detector_versions),
                    _json_dumps(list(control.original_box)) if control.original_box else None,
                    _json_dumps(list(control.refined_box)) if control.refined_box else None,
                    _json_dumps(control.confidences),
                    _json_dumps(control.reasons),
                ),
            )

    def _prune_inactive(self, conn: sqlite3.Connection, app_id: str) -> None:
        """Conserva solo los ultimos perfiles inactivos no VALIDADO por aplicacion."""
        rows = conn.execute(
            "SELECT profile_id FROM calibration_profiles WHERE machine_id = ? AND app_id = ? "
            "AND is_active = 0 AND status != ? ORDER BY updated_at DESC, created_at DESC",
            (self.machine_id, app_id, CalibrationState.VALIDADO.value),
        ).fetchall()
        for row in rows[MAX_INACTIVE_PROFILES_PER_APP:]:
            conn.execute(
                "DELETE FROM calibration_profiles WHERE profile_id = ? AND machine_id = ?",
                (row["profile_id"], self.machine_id),
            )

    def mark_obsolete(self, app_id: str, reason: str, profile_id: Optional[str] = None) -> int:
        """Marca OBSOLETO y desactiva los perfiles de una aplicacion (o uno concreto).

        Devuelve el numero de perfiles afectados. No borra datos.
        """
        with self._lock:
            conn = self._ensure_ready(for_write=True)
            assert conn is not None
            now = _now_iso()
            params: List[Any] = [CalibrationState.OBSOLETO.value, str(reason or ""), now, self.machine_id, app_id]
            sql = (
                "UPDATE calibration_profiles SET status = ?, is_active = 0, obsolete_reason = ?, "
                "absolute_cache = '{}', updated_at = ? WHERE machine_id = ? AND app_id = ?"
            )
            if profile_id:
                sql += " AND profile_id = ?"
                params.append(profile_id)
            else:
                sql += " AND status != ?"
                params.append(CalibrationState.OBSOLETO.value)
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(sql, params)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            count = int(cur.rowcount or 0)
            if count:
                logger.info("Perfiles de calibracion marcados OBSOLETO app=%s n=%d motivo=%s", app_id, count, reason)
            return count

    def update_absolute_cache(self, profile_id: str, cache: Dict[str, Any]) -> bool:
        """Sustituye la cache de coordenadas absolutas de un perfil (no altera la geometria relativa)."""
        with self._lock:
            conn = self._ensure_ready(for_write=True)
            assert conn is not None
            cur = conn.execute(
                "UPDATE calibration_profiles SET absolute_cache = ?, updated_at = ? "
                "WHERE profile_id = ? AND machine_id = ?",
                (_json_dumps(cache or {}), _now_iso(), profile_id, self.machine_id),
            )
            return bool(cur.rowcount)

    def delete_profiles(self, app_id: str) -> int:
        """Borra explicitamente todos los perfiles de una aplicacion en este equipo."""
        with self._lock:
            conn = self._ensure_ready(for_write=True)
            assert conn is not None
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM calibration_controls WHERE machine_id = ? AND app_id = ?",
                    (self.machine_id, app_id),
                )
                cur = conn.execute(
                    "DELETE FROM calibration_profiles WHERE machine_id = ? AND app_id = ?",
                    (self.machine_id, app_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            count = int(cur.rowcount or 0)
            logger.info("Perfiles de calibracion borrados app=%s n=%d", app_id, count)
            return count

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def get_active_profile(
        self, app_id: str, window_fingerprint: Optional[str] = None
    ) -> Optional[CalibrationProfile]:
        """Ultimo perfil VALIDADO activo de la aplicacion en este equipo.

        Con ``window_fingerprint`` devuelve el activo de esa huella; sin ella,
        el activo mas reciente de cualquier huella (la vigencia la decide
        ``calibration_validity``).
        """
        with self._lock:
            conn = self._ensure_ready(for_write=False)
            if conn is None:
                return None
            sql = (
                "SELECT * FROM calibration_profiles WHERE machine_id = ? AND app_id = ? "
                "AND is_active = 1 AND status = ?"
            )
            params: List[Any] = [self.machine_id, app_id, CalibrationState.VALIDADO.value]
            if window_fingerprint is not None:
                sql += " AND window_fingerprint = ?"
                params.append(window_fingerprint)
            sql += " ORDER BY updated_at DESC, created_at DESC LIMIT 1"
            row = conn.execute(sql, params).fetchone()
            return self._row_to_profile(conn, row) if row is not None else None

    def get_profile(self, profile_id: str) -> Optional[CalibrationProfile]:
        with self._lock:
            conn = self._ensure_ready(for_write=False)
            if conn is None:
                return None
            row = conn.execute(
                "SELECT * FROM calibration_profiles WHERE profile_id = ? AND machine_id = ?",
                (profile_id, self.machine_id),
            ).fetchone()
            return self._row_to_profile(conn, row) if row is not None else None

    def list_profiles(self, app_id: Optional[str] = None) -> List[CalibrationProfile]:
        """Perfiles de este equipo (todos los estados), mas recientes primero."""
        with self._lock:
            conn = self._ensure_ready(for_write=False)
            if conn is None:
                return []
            sql = "SELECT * FROM calibration_profiles WHERE machine_id = ?"
            params: List[Any] = [self.machine_id]
            if app_id is not None:
                sql += " AND app_id = ?"
                params.append(app_id)
            sql += " ORDER BY updated_at DESC, created_at DESC"
            return [self._row_to_profile(conn, row) for row in conn.execute(sql, params).fetchall()]

    def list_active_profiles(self, app_id: str) -> List[CalibrationProfile]:
        """Todos los perfiles VALIDADO activos de una aplicacion (uno por huella)."""
        return [
            p for p in self.list_profiles(app_id)
            if p.is_active and p.status == CalibrationState.VALIDADO
        ]

    def get_control(self, app_id: str, control_id: str) -> Optional[CalibratedControlRecord]:
        """Control del perfil activo mas reciente de la aplicacion."""
        profile = self.get_active_profile(app_id)
        if profile is None:
            return None
        return profile.get_control(control_id)

    def _row_to_profile(self, conn: sqlite3.Connection, row: sqlite3.Row) -> CalibrationProfile:
        controls = [
            self._row_to_control(c)
            for c in conn.execute(
                "SELECT * FROM calibration_controls WHERE profile_id = ? AND machine_id = ? "
                "ORDER BY control_id",
                (row["profile_id"], self.machine_id),
            ).fetchall()
        ]
        dps = None
        if row["display_pixel_width"] is not None and row["display_pixel_height"] is not None:
            dps = (int(row["display_pixel_width"]), int(row["display_pixel_height"]))
        cs = None
        if row["client_width"] is not None and row["client_height"] is not None:
            cs = (int(row["client_width"]), int(row["client_height"]))
        return CalibrationProfile(
            profile_id=row["profile_id"],
            machine_id=row["machine_id"],
            app_id=row["app_id"],
            topology_fingerprint=row["topology_fingerprint"] or "",
            window_fingerprint=row["window_fingerprint"] or "",
            display_id=row["display_id"] or "",
            scale_factor=float(row["scale_factor"]) if row["scale_factor"] is not None else None,
            dpi=int(row["dpi"]) if row["dpi"] is not None else None,
            display_pixel_size=dps,
            orientation=row["orientation"] or "",
            window_state=row["window_state"] or "",
            client_size=cs,
            platform=row["platform"] or "",
            status=_as_state(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            controls=controls,
            absolute_cache=_json_loads(row["absolute_cache"], {}),
            metadata=_json_loads(row["metadata"], {}),
            is_active=bool(row["is_active"]),
            obsolete_reason=row["obsolete_reason"],
        )

    @staticmethod
    def _row_to_control(row: sqlite3.Row) -> CalibratedControlRecord:
        return CalibratedControlRecord(
            control_id=row["control_id"],
            app_id=row["app_id"],
            name=row["name"] or "",
            control_type=row["control_type"] or "element",
            semantic_state=_as_state(row["semantic_state"]),
            geometric_state=_as_state(row["geometric_state"]),
            action_state=_as_state(row["action_state"]),
            client_box_normalized=tuple(_json_loads(row["client_box_normalized"], [0, 0, 0, 0])),  # type: ignore[arg-type]
            client_box_px=_json_loads(row["client_box_px"], None),
            safe_point_normalized=_json_loads(row["safe_point_normalized"], None),
            interaction_method=row["interaction_method"] or "none",
            provenance=_json_loads(row["provenance"], []),
            detector_versions=_json_loads(row["detector_versions"], {}),
            original_box=_json_loads(row["original_box"], None),
            refined_box=_json_loads(row["refined_box"], None),
            confidences=_json_loads(row["confidences"], {}),
            reasons=_json_loads(row["reasons"], []),
        )


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================


_STORE: Optional[CalibrationProfileStore] = None
_STORE_LOCK = threading.Lock()


def get_calibration_profile_store() -> CalibrationProfileStore:
    """Almacen global del proceso (base del proyecto y ``machine_id`` actual)."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = CalibrationProfileStore()
        return _STORE


__all__ = [
    "CalibrationState",
    "CalibratedControlRecord",
    "CalibrationProfile",
    "CalibrationProfileStore",
    "CalibrationStoreError",
    "CalibrationStoreBlocked",
    "INTERACTION_METHODS",
    "ACCESSIBILITY_PROVENANCE",
    "MIN_INDEPENDENT_VISUAL_SOURCES",
    "check_control_record",
    "check_profile",
    "default_db_path",
    "get_calibration_profile_store",
]
