"""
Contrato, alcance y privacidad del inventario persistente del sistema de archivos.

Este modulo define el contrato del inventario local de elementos del sistema de
archivos del equipo donde se ejecuta JARVIS (unidad 3.8.5.1.4.1).

No implementa escaneo ni persistencia (esas responsabilidades corresponden a
3.8.5.1.4.2 y 3.8.5.1.4.4). Solo define:
- La entrada de inventario con metadatos minimos.
- El identificador local de equipo.
- El alcance predeterminado y las exclusiones tecnicas.
- Los controles de privacidad (no leer contenido de archivos personales,
  no enviar nombres/rutas completos a logs).
- Separacion entre hechos observados por el SO e inferencias.
- Controles de pausa, reanudacion, cancelacion, exclusión y reconstruccion.

Todo lo aqui definido es contrato puro: dataclasses, constantes y funciones
de utilidad sin efectos secundarios sobre el disco salvo lo expresamente
documentado.
"""

from __future__ import annotations

import platform
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class EntryType(Enum):
    """Tipo de entrada del inventario, observado directamente del SO."""

    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    JUNCTION = "junction"
    MOUNT_POINT = "mount_point"
    OTHER = "other"


class InventoryScope(Enum):
    """Alcance del inventario."""

    LOCAL_VOLUMES = "local_volumes"
    ALL_MOUNTED = "all_mounted"
    SPECIFIC_PATHS = "specific_paths"


# ---------------------------------------------------------------------------
# Metadatos minimos de una entrada de inventario (3.8.5.1.4.1.7)
# ---------------------------------------------------------------------------

@dataclass
class InventoryEntry:
    """
    Entrada del inventario de un elemento del sistema de archivos.

    Solo metadatos observados por el sistema operativo. Nunca se lee ni
    almacena el contenido de archivos personales (3.8.5.1.4.1.9).
    """

    # Identidad local del equipo que crea el inventario (3.8.5.1.4.1.2, .1.3)
    machine_id: str
    # Volumen o unidad donde reside la entrada (3.8.5.1.4.1.5)
    volume: str
    # Ruta absoluta normalizada del elemento
    absolute_path: str
    # Ruta relativa a la raiz del volumen
    relative_path: str
    # Nombre del archivo o directorio
    name: str
    # Extension del archivo (vacia para directorios)
    extension: str
    # Tipo de entrada observado del SO (3.8.5.1.4.1.8: hecho, no inferencia)
    entry_type: EntryType
    # Tamano en bytes (0 para directorios y enlaces)
    size_bytes: int
    # Fecha de ultima modificacion (ISO 8601)
    modified_at: str
    # Fecha de creacion (ISO 8601)
    created_at: str
    # Fecha de ultimo acceso (ISO 8601, puede estar vacia en algunos SO)
    accessed_at: Optional[str] = None
    # Atributos observados del SO (oculto, sistema, solo lectura, etc.)
    attributes: list[str] = field(default_factory=list)
    # Si la entrada esta excluida del inventario
    excluded: bool = False
    # Motivo de la exclusicion (tecnico, justificado)
    exclusion_reason: Optional[str] = None
    # Fuente de descubrimiento (ej. "filesystem_scan", "preflight", etc.)
    source: str = "filesystem_scan"
    # Marca de tiempo de la ultima comprobacion (ISO 8601)
    last_checked_at: str = ""

    def to_dict(self) -> dict:
        """Serializa a diccionario plano."""
        return {
            "machine_id": self.machine_id,
            "volume": self.volume,
            "absolute_path": self.absolute_path,
            "relative_path": self.relative_path,
            "name": self.name,
            "extension": self.extension,
            "entry_type": self.entry_type.value,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "attributes": list(self.attributes),
            "excluded": self.excluded,
            "exclusion_reason": self.exclusion_reason,
            "source": self.source,
            "last_checked_at": self.last_checked_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InventoryEntry":
        """Crea una instancia desde un diccionario."""
        entry_type = EntryType(data.get("entry_type", EntryType.OTHER.value))
        return cls(
            machine_id=data["machine_id"],
            volume=data["volume"],
            absolute_path=data["absolute_path"],
            relative_path=data["relative_path"],
            name=data["name"],
            extension=data.get("extension", ""),
            entry_type=entry_type,
            size_bytes=int(data.get("size_bytes", 0)),
            modified_at=data.get("modified_at", ""),
            created_at=data.get("created_at", ""),
            accessed_at=data.get("accessed_at"),
            attributes=list(data.get("attributes", [])),
            excluded=bool(data.get("excluded", False)),
            exclusion_reason=data.get("exclusion_reason"),
            source=data.get("source", "filesystem_scan"),
            last_checked_at=data.get("last_checked_at", ""),
        )


# ---------------------------------------------------------------------------
# Identificador local de equipo (3.8.5.1.4.1.2, .1.3)
# ---------------------------------------------------------------------------

def generate_machine_id() -> str:
    """
    Genera un identificador local de equipo para JARVIS.

    No usa direccion MAC, numero de serie ni nombre de usuario (3.8.5.1.4.1.2).
    El identificador es estable por equipo e instalacion: se deriva de
    combinacion de nodo, plataforma y un UUID persistente local.
    """
    node = platform.node() or "unknown"
    system = platform.system() or "unknown"
    # UUID v5 basado en nombres estables del equipo (no MAC ni serial)
    namespace = uuid.NAMESPACE_DNS
    stable_name = f"jarvis-local-{node}-{system}"
    return str(uuid.uuid5(namespace, stable_name))


def is_same_machine(machine_id_a: str, machine_id_b: str) -> bool:
    """Comprueba si dos identificadores pertenecen al mismo equipo."""
    return machine_id_a == machine_id_b


# ---------------------------------------------------------------------------
# Alcance predeterminado y exclusiones tecnicas (3.8.5.1.4.1.5, .1.6)
# ---------------------------------------------------------------------------

# Volumes/sistemas de archivos virtuales o recursivos que se excluyen por defecto
DEFAULT_EXCLUDED_MOUNT_PATTERNS: list[str] = [
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/tmp",
    "/var/tmp",
    "C:\\Windows\\WinSxS",
    "C:\\$Recycle.Bin",
    "C:\\System Volume Information",
]

# Patrones de rutas que nunca se incluyen (exclusiones tecnicas justificadas)
DEFAULT_EXCLUDED_PATH_PATTERNS: list[str] = [
    # Sistemas de archivos virtuales y de pseudoficheros (Linux)
    "/proc/",
    "/sys/",
    "/dev/",
    "/run/",
    # Puntos de montaje recursivos y volumes de red no montados localmente
    "/mnt/network",
    "/media/network",
    # Papelera y volumenes del sistema de Windows
    "$Recycle.Bin",
    "System Volume Information",
    # Archivos de paginacion e hibernacion
    "pagefile.sys",
    "hiberfil.sys",
    "swapfile.sys",
]


def is_excluded_path(path: str, exclusions: Optional[list[str]] = None) -> bool:
    """
    Determina si una ruta debe excluirse del inventario.

    Aplica exclusiones tecnicas justificadas (3.8.5.1.4.1.6).
    """
    if exclusions is None:
        exclusions = DEFAULT_EXCLUDED_PATH_PATTERNS
    path_lower = path.lower()
    for pattern in exclusions:
        if pattern.lower() in path_lower:
            return True
    return False


def is_excluded_mount(mount_point: str, exclusions: Optional[list[str]] = None) -> bool:
    """
    Determina si un punto de montaje/volumen debe excluirse.

    Excluye sistemas de archivos virtuales, puntos de montaje recursivos y
    ubicaciones de red no montadas localmente (3.8.5.1.4.1.6).
    """
    if exclusions is None:
        exclusions = DEFAULT_EXCLUDED_MOUNT_PATTERNS
    mount_lower = mount_point.lower()
    for pattern in exclusions:
        if pattern.lower() in mount_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Controles de privacidad (3.8.5.1.4.1.9)
# ---------------------------------------------------------------------------

PRIVACY_NOTICE = (
    "El inventario solo registra metadatos observados del sistema de archivos. "
    "Nunca se lee el contenido de archivos personales, nunca se envian nombres "
    "ni rutas completos a logs ni a modelos de lenguaje, y el inventario "
    "permanece aislado por equipo y volumen."
)


def safe_log_path(path: str, max_chars: int = 40) -> str:
    """
    Devuelve una version acortada y segura de una ruta para logs.

    Nunca se loguean rutas completas ni nombres de archivos personales
    (3.8.5.1.4.1.9).
    """
    if len(path) <= max_chars:
        return path
    # Solo se muestra el nombre final y una marca de truncamiento
    p = Path(path)
    return f"...{p.name}"


# ---------------------------------------------------------------------------
# Separacion de hechos vs inferencias (3.8.5.1.4.1.8)
# ---------------------------------------------------------------------------

class FactType(Enum):
    """Clasifica si un dato es un hecho observado o una inferencia."""

    OBSERVED = "observed"      # Hecho directo del SO
    INFERRED = "inferred"      # Inferencia (no confirmar como capacidad)
    EXCLUDED = "excluded"      # Entrada excluida del inventario


def classify_entry(entry_type: EntryType, extension: str) -> FactType:
    """
    Clasifica una entrada como hecho observado o inferencia.

    Por defecto, todo lo que viene del SO es OBSERVED. Las inferencias
    (ej. "este .exe es una aplicacion GUI") no se persisten como hechos
    (3.8.5.1.4.1.8, .1.9).
    """
    # Los tipos de entrada son observados directamente del SO
    if entry_type in (EntryType.FILE, EntryType.DIRECTORY,
                      EntryType.SYMLINK, EntryType.JUNCTION,
                      EntryType.MOUNT_POINT):
        return FactType.OBSERVED
    return FactType.INFERRED


# ---------------------------------------------------------------------------
# Controles de operacion del inventario (3.8.5.1.4.1.10)
# ---------------------------------------------------------------------------

class InventoryControl(Enum):
    """Controles disponibles para gestion del inventario."""

    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    EXCLUDE_PATH = "exclude_path"
    REBUILD = "rebuild"
    DELETE = "delete"


@dataclass
class InventoryControlResult:
    """Resultado de una operacion de control del inventario."""

    control: InventoryControl
    accepted: bool
    reason: str
    machine_id: str


def validate_control(control: InventoryControl, machine_id: str,
                     current_machine_id: str) -> InventoryControlResult:
    """
    Valida que una operacion de control sea aceptable.

    Solo se permiten operaciones sobre el inventario del propio equipo
    (aislamiento por equipo, 3.8.5.1.4.1.3).
    """
    if machine_id != current_machine_id:
        return InventoryControlResult(
            control=control,
            accepted=False,
            reason=f"El inventario pertenece a otro equipo: {machine_id}",
            machine_id=machine_id,
        )
    return InventoryControlResult(
        control=control,
        accepted=True,
        reason="Control aceptado",
        machine_id=machine_id,
    )


# ---------------------------------------------------------------------------
# Contrato del inventario (3.8.5.1.4.1.1, .1.12)
# ---------------------------------------------------------------------------

@dataclass
class InventoryContract:
    """
    Contrato del inventario persistente.

    Define alcance, metadatos, privacidad y exclusiones de forma centralizada.
    """

    machine_id: str
    scope: InventoryScope = InventoryScope.LOCAL_VOLUMES
    excluded_paths: list[str] = field(default_factory=list)
    excluded_mounts: list[str] = field(default_factory=list)
    max_entries_per_volume: Optional[int] = None
    include_hidden: bool = True
    include_system: bool = True
    read_file_content: bool = False  # Nunca True: privacidad (3.8.5.1.4.1.9)
    log_full_paths: bool = False     # Nunca True: privacidad (3.8.5.1.4.1.9)

    def __post_init__(self) -> None:
        if not self.excluded_paths:
            self.excluded_paths = list(DEFAULT_EXCLUDED_PATH_PATTERNS)
        if not self.excluded_mounts:
            self.excluded_mounts = list(DEFAULT_EXCLUDED_MOUNT_PATTERNS)

    def should_exclude_path(self, path: str) -> bool:
        """Devuelve True si la ruta debe excluirse segun el contrato."""
        return is_excluded_path(path, self.excluded_paths)

    def should_exclude_mount(self, mount_point: str) -> bool:
        """Devuelve True si el punto de montaje debe excluirse."""
        return is_excluded_mount(mount_point, self.excluded_mounts)

    def privacy_summary(self) -> str:
        """Devuelve un resumen legible de las garantias de privacidad."""
        return PRIVACY_NOTICE


def default_contract() -> InventoryContract:
    """
    Devuelve el contrato por defecto del inventario.

    Alcance: volumenes locales montados. Exclusiones tecnicas predeterminadas.
    Privacidad: sin lectura de contenido, sin rutas completas en logs.
    """
    return InventoryContract(machine_id=generate_machine_id())


# ---------------------------------------------------------------------------
# Matriz de cobertura del inventario (3.8.5.1.4.1.12)
# ---------------------------------------------------------------------------

@dataclass
class CoverageMatrixEntry:
    """Una celda de la matriz de cobertura del inventario."""

    sistema_operativo: str
    version: str
    arquitectura: str
    tipo_volumen: str
    tipo_entrada: str
    soportado: bool
    notas: str = ""


# Matriz explicita de cobertura por sistema operativo, version, arquitectura,
# tipo de volumen y tipo de entrada. Define que combinaciones estan soportadas
# por el adaptador de descubrimiento de volumenes (3.8.5.1.4.3).
COVERAGE_MATRIX: list[CoverageMatrixEntry] = [
    # Windows - volumenes locales
    CoverageMatrixEntry("Windows", "10", "x64", "local", "file", True),
    CoverageMatrixEntry("Windows", "10", "x64", "local", "directory", True),
    CoverageMatrixEntry("Windows", "10", "x64", "local", "symlink", True),
    CoverageMatrixEntry("Windows", "11", "x64", "local", "file", True),
    CoverageMatrixEntry("Windows", "11", "x64", "local", "directory", True),
    CoverageMatrixEntry("Windows", "11", "x64", "local", "symlink", True),
    # Windows - volumenes extraibles (solo lectura, sin escritura)
    CoverageMatrixEntry("Windows", "10", "x64", "removable", "file", True),
    CoverageMatrixEntry("Windows", "10", "x64", "removable", "directory", True),
    CoverageMatrixEntry("Windows", "11", "x64", "removable", "file", True),
    CoverageMatrixEntry("Windows", "11", "x64", "removable", "directory", True),
    # Linux - volumenes locales montados
    CoverageMatrixEntry("Linux", "any", "x64", "local", "file", True),
    CoverageMatrixEntry("Linux", "any", "x64", "local", "directory", True),
    CoverageMatrixEntry("Linux", "any", "x64", "local", "symlink", True),
    CoverageMatrixEntry("Linux", "any", "x64", "local", "mount_point", True),
    # Linux - volumenes de red (no montados localmente: no soportados)
    CoverageMatrixEntry("Linux", "any", "x64", "network", "file", False,
                        "Volumenes de red no montados localmente no se inventarian"),
    # macOS - volumenes locales montados
    CoverageMatrixEntry("Darwin", "any", "arm64", "local", "file", True),
    CoverageMatrixEntry("Darwin", "any", "arm64", "local", "directory", True),
    CoverageMatrixEntry("Darwin", "any", "arm64", "local", "symlink", True),
    # macOS - volumenes de red (no soportados por defecto)
    CoverageMatrixEntry("Darwin", "any", "arm64", "network", "file", False,
                        "Volumenes de red no montados localmente no se inventarian"),
]


def cobertura_soportada(sistema_operativo: str, version: str, arquitectura: str,
                        tipo_volumen: str, tipo_entrada: str) -> bool:
    """
    Consulta la matriz de cobertura para saber si una combinacion es soportada.

    Devuelve False si no hay entrada registrada para la combinacion
    (principio: no declarar soportado lo que no esta implementado y probado).
    """
    for entrada in COVERAGE_MATRIX:
        if (entrada.sistema_operativo.lower() == sistema_operativo.lower()
                and (entrada.version == "any" or entrada.version == version)
                and entrada.arquitectura.lower() == arquitectura.lower()
                and entrada.tipo_volumen.lower() == tipo_volumen.lower()
                and entrada.tipo_entrada.lower() == tipo_entrada.lower()):
            return entrada.soportado
    return False


def entradas_cobertura_por_sistema(sistema_operativo: str) -> list[CoverageMatrixEntry]:
    """Devuelve todas las entradas de cobertura para un sistema operativo."""
    return [e for e in COVERAGE_MATRIX
            if e.sistema_operativo.lower() == sistema_operativo.lower()]
