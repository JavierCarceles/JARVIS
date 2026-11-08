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

import ctypes
import platform
import subprocess
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
    "/private/var/vm",
    "/private/var/folders",
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
    # macOS - volumenes locales montados (Intel x86_64)
    CoverageMatrixEntry("Darwin", "any", "x64", "local", "file", True),
    CoverageMatrixEntry("Darwin", "any", "x64", "local", "directory", True),
    CoverageMatrixEntry("Darwin", "any", "x64", "local", "symlink", True),
    # macOS - volumenes extraibles (Apple Silicon)
    CoverageMatrixEntry("Darwin", "any", "arm64", "removable", "file", True),
    CoverageMatrixEntry("Darwin", "any", "arm64", "removable", "directory", True),
    # macOS - volumenes extraibles (Intel x86_64)
    CoverageMatrixEntry("Darwin", "any", "x64", "removable", "file", True),
    CoverageMatrixEntry("Darwin", "any", "x64", "removable", "directory", True),
    # macOS - volumenes virtuales (detectados; excluidos por defecto del inventario)
    CoverageMatrixEntry("Darwin", "any", "arm64", "virtual", "file", True),
    CoverageMatrixEntry("Darwin", "any", "arm64", "virtual", "directory", True),
    CoverageMatrixEntry("Darwin", "any", "x64", "virtual", "file", True),
    CoverageMatrixEntry("Darwin", "any", "x64", "virtual", "directory", True),
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


# ---------------------------------------------------------------------------
# Deteccion de sistema operativo, arquitectura y version (3.8.5.1.4.3.1)
# ---------------------------------------------------------------------------

class SistemaOperativo(Enum):
    """Sistemas operativos detectables mediante APIs del sistema (platform)."""

    WINDOWS = "Windows"
    LINUX = "Linux"
    DARWIN = "Darwin"  # macOS
    DESCONOCIDO = "Desconocido"


@dataclass
class InfoSistema:
    """
    Informacion del sistema operativo detectada mediante APIs del sistema.

    Todos los campos se obtienen del modulo `platform` de la biblioteca
    estandar (APIs del SO), nunca deducidos a partir de nombres de rutas ni
    inspeccionando el sistema de archivos (3.8.5.1.4.3.1).
    """

    sistema_operativo: str      # platform.system(): "Windows", "Linux", "Darwin"...
    version: str                # platform.release() o platform.version()
    arquitectura: str           # platform.machine() normalizado: "x64", "x86", "arm64"...
    nombre_plataforma: str      # platform.platform()
    procesador: str             # platform.processor()


def normalizar_arquitectura(maquina: str) -> str:
    """
    Normaliza el identificador de arquitectura de platform.machine().

    Solo traduce el valor devuelto por la API del sistema; no infiere
    arquitectura a partir de rutas ni de cualquier otro dato del filesystem.
    """
    m = maquina.lower()
    if m in ("amd64", "x86_64", "x64"):
        return "x64"
    if m in ("i386", "i686", "x86", "x86-32"):
        return "x86"
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("armv7l", "armv7"):
        return "armv7"
    return maquina


def detectar_sistema() -> InfoSistema:
    """
    Detecta sistema operativo, version y arquitectura mediante APIs del sistema.

    Utiliza exclusivamente el modulo `platform` de la biblioteca estandar:
    - sistema operativo: platform.system()
    - version: platform.release() y, si falta, platform.version()
    - arquitectura: platform.machine() (normalizada)
    - nombre completo: platform.platform()
    - procesador: platform.processor()

    No deduce el SO a partir de nombres de rutas ni inspecciona el sistema de
    archivos para determinar el SO (3.8.5.1.4.3.1).
    """
    sistema = platform.system() or "Desconocido"
    release = platform.release() or ""
    version_detallada = platform.version() or ""
    version = release if release else version_detallada
    maquina = platform.machine() or ""
    arquitectura = normalizar_arquitectura(maquina) if maquina else maquina
    nombre_plataforma = platform.platform() or ""
    procesador = platform.processor() or ""

    return InfoSistema(
        sistema_operativo=sistema,
        version=version,
        arquitectura=arquitectura,
        nombre_plataforma=nombre_plataforma,
        procesador=procesador,
    )


def es_sistema_soportado(sistema_operativo: str, arquitectura: str) -> bool:
    """
    Indica si el adaptador de descubrimiento de volumenes soporta la
    combinacion SO/arquitectura dada, consultando la matriz de cobertura.

    Se considera soportado si existe al menos una entrada de cobertura para
    ese SO y arquitectura con cualquier tipo de volumen y tipo de entrada.
    No declara soporte por inferencia: solo lo que esta registrado en la
    matriz (3.8.5.1.4.3.8).
    """
    for entrada in COVERAGE_MATRIX:
        if (entrada.sistema_operativo.lower() == sistema_operativo.lower()
                and entrada.arquitectura.lower() == arquitectura.lower()
                and entrada.soportado):
            return True
    return False


# ---------------------------------------------------------------------------
# Enumeracion de volumenes Windows (3.8.5.1.4.3.2)
# ---------------------------------------------------------------------------

class VolumeType(Enum):
    """Tipo de volumen/unidad observado del SO, compartido por los adaptadores
    de descubrimiento de volumenes (Windows y Linux)."""

    UNKNOWN = "unknown"
    NO_ROOT_DIR = "no_root_dir"
    REMOVABLE = "removable"
    FIXED = "fixed"
    REMOTE = "remote"
    CD_ROM = "cd_rom"
    RAM_DISK = "ram_disk"
    VIRTUAL = "virtual"


_VOLUME_TYPE_BY_CODE: dict[int, VolumeType] = {
    0: VolumeType.UNKNOWN,
    1: VolumeType.NO_ROOT_DIR,
    2: VolumeType.REMOVABLE,
    3: VolumeType.FIXED,
    4: VolumeType.REMOTE,
    5: VolumeType.CD_ROM,
    6: VolumeType.RAM_DISK,
}


@dataclass
class VolumeInfo:
    """
    Informacion de un volumen/unidad de Windows observada del SO.

    Solo metadatos del volumen (letra, tipo, disponibilidad, sistema de archivos,
    etiqueta). Nunca se lee el contenido del volumen (3.8.5.1.4.1.9).
    """

    letra: str                    # Ej. "C:"
    ruta_raiz: str                # Ej. "C:\\"
    tipo: VolumeType              # Tipo de unidad observado
    disponible: bool              # True si el volumen esta listo para leer
    sistema_archivos: str = ""    # Ej. "NTFS", "FAT32"
    etiqueta_volumen: str = ""    # Etiqueta del volumen


def _letra_de_indice_bit(indice_bit: int) -> str:
    """Devuelve la letra de unidad correspondiente a un indice de bit (0=A, 1=B...)."""
    return f"{chr(ord('A') + indice_bit)}:"


def enumerar_volumenes_windows() -> list[VolumeInfo]:
    """
    Enumerar en Windows unidades y volumenes locales, letras, puntos de montaje,
    tipo de unidad y estado de disponibilidad.

    Reutiliza APIs de Windows mediante `ctypes` (biblioteca estandar), sin
    dependencias de terceros:
    - `GetLogicalDrives` para obtener la mascara de unidades logicas.
    - `GetDriveType` para clasificar cada unidad (fija, extraíble, CD-ROM, red, RAM, etc.).
    - `GetVolumeInformation` para sistema de archivos y etiqueta, solo cuando la
      unidad esta disponible (no falla si no se puede leer).

    Devuelve una lista de `VolumeInfo`, una por unidad detectada, ordenada por
    letra de unidad. Las unidades sin raiz (p.ej. lector de tarjetas vacio) se
    reportan con `disponible=False`.
    """
    kernel32 = ctypes.windll.kernel32

    mascara = kernel32.GetLogicalDrives()
    if mascara == 0:
        return []

    volumenes: list[VolumeInfo] = []
    for indice in range(26):
        if not (mascara >> indice) & 1:
            continue
        letra = _letra_de_indice_bit(indice)
        ruta_raiz = f"{letra}\\"

        codigo_tipo = kernel32.GetDriveTypeW(ruta_raiz)
        tipo = _VOLUME_TYPE_BY_CODE.get(codigo_tipo, VolumeType.UNKNOWN)

        # GetDriveType devuelve DRIVE_NO_ROOT_DIR (1) cuando la unidad no tiene
        # medio insertado (p.ej. lector de tarjetas vacio). La unidad existe pero
        # no esta disponible para lectura.
        disponible = codigo_tipo != 1

        sistema_archivos = ""
        etiqueta_volumen = ""
        if disponible:
            nombre_volumen = ctypes.create_unicode_buffer(256)
            sistema_archivos_buf = ctypes.create_unicode_buffer(256)
            numero_serie = ctypes.c_ulong()
            longitud_maxima = ctypes.c_ulong()
            banderas = ctypes.c_ulong()
            ok = kernel32.GetVolumeInformationW(
                ruta_raiz,
                nombre_volumen,
                ctypes.sizeof(nombre_volumen),
                ctypes.byref(numero_serie),
                ctypes.byref(longitud_maxima),
                ctypes.byref(banderas),
                sistema_archivos_buf,
                ctypes.sizeof(sistema_archivos_buf),
            )
            if ok:
                etiqueta_volumen = nombre_volumen.value or ""
                sistema_archivos = sistema_archivos_buf.value or ""

        volumenes.append(
            VolumeInfo(
                letra=letra,
                ruta_raiz=ruta_raiz,
                tipo=tipo,
                disponible=disponible,
                sistema_archivos=sistema_archivos,
                etiqueta_volumen=etiqueta_volumen,
            )
        )

    return volumenes


# ---------------------------------------------------------------------------
# Enumeracion de volumenes Linux (3.8.5.1.4.3.3)
# ---------------------------------------------------------------------------

# Sistemas de archivos virtuales/pseudoficheros del kernel de Linux. Se
# detectan pero el contrato por defecto los excluye del inventario
# (3.8.5.1.4.1.6, DEFAULT_EXCLUDED_MOUNT_PATTERNS).
_LINUX_VIRTUAL_FSTYPES: frozenset[str] = frozenset({
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2",
    "pstore", "mqueue", "binfmt_misc", "securityfs", "efivarfs", "configfs",
    "debugfs", "tracefs", "fusectl", "hugetlbfs", "ramfs", "rootfs",
    "overlay", "squashfs", "iso9660",
})

# Sistemas de archivos de red (no montados localmente como volumen de bloque).
_LINUX_NETWORK_FSTYPES: frozenset[str] = frozenset({
    "nfs", "nfs4", "cifs", "cifsdfs", "smbfs", "sshfs", "fuse.sshfs",
    "glusterfs", "ceph", "ocfs2", "lustre", "ncp", "smb3",
})

# Sistemas de archivos tipicamente asociados a medios extraibles.
_LINUX_REMOVABLE_FSTYPES: frozenset[str] = frozenset({
    "vfat", "exfat", "ntfs-3g", "ntfs", "fuseblk",
})

# Sistemas de archivos locales de disco.
_LINUX_LOCAL_FSTYPES: frozenset[str] = frozenset({
    "ext4", "ext3", "ext2", "xfs", "btrfs", "zfs", "jfs", "reiserfs",
    "f2fs", "nilfs2", "ntfs-3g", "ntfs", "fuseblk",
})


# ---------------------------------------------------------------------------
# Clasificadores de tipos de sistema de archivos macOS (3.8.5.1.4.3.4)
# ---------------------------------------------------------------------------

# Sistemas de archivos virtuales/pseudoficheros del kernel de macOS.
_MACOS_VIRTUAL_FSTYPES: frozenset[str] = frozenset({
    "devfs", "fdescfs", "tmpfs", "autofs",
})

# Sistemas de archivos de red en macOS.
_MACOS_NETWORK_FSTYPES: frozenset[str] = frozenset({
    "nfs", "smbfs", "afp", "webdav",
})

# Sistemas de archivos tipicamente asociados a medios extraibles en macOS.
_MACOS_REMOVABLE_FSTYPES: frozenset[str] = frozenset({
    "exfat", "msdos",
})


def _clasificar_tipo_volumen_linux(
    dispositivo: str, fstype: str, opciones: str, mount_point: str
) -> VolumeType:
    """
    Clasifica un montaje de Linux en local, virtual, de red o extraible.

    La clasificacion se basa unicamente en el tipo de sistema de archivos
    reportado por el kernel (/proc/mounts), en el punto de montaje y en las
    opciones de montaje; nunca infiere el SO a partir de rutas (3.8.5.1.4.3.1)
    ni declara soporte sin evidencia del adaptador (3.8.5.1.4.3.8).
    """
    f = (fstype or "").lower()
    o = (opciones or "").lower()
    mp = (mount_point or "").lower()
    d = (dispositivo or "").lower()

    # 1. Sistemas de archivos virtuales/pseudoficheros del kernel.
    if f in _LINUX_VIRTUAL_FSTYPES:
        return VolumeType.VIRTUAL
    if mp in ("/proc", "/sys", "/dev", "/run", "/tmp", "/var/tmp"):
        return VolumeType.VIRTUAL
    if "noauto" in o and d.startswith(("none", "tmpfs", "cgroup")):
        return VolumeType.VIRTUAL

    # 2. Sistemas de archivos de red.
    if f in _LINUX_NETWORK_FSTYPES:
        return VolumeType.REMOTE
    if "_netdev" in o or "nfs" in o or "cifs" in o:
        return VolumeType.REMOTE

    # 3. Medios extraibles (USB, discos externos) montados bajo /media o /mnt.
    if f in _LINUX_REMOVABLE_FSTYPES and (
        mp.startswith("/media/") or mp.startswith("/mnt/") or "removable" in o
    ):
        return VolumeType.REMOVABLE

    # 4. Sistemas de archivos locales de disco.
    if f in _LINUX_LOCAL_FSTYPES:
        return VolumeType.FIXED

    return VolumeType.UNKNOWN


def _clasificar_tipo_volumen_macos(
    dispositivo: str, fstype: str, opciones: str, mount_point: str
) -> VolumeType:
    """
    Clasifica un volumen montado de macOS en local, virtual, de red o extraible.

    La clasificacion se basa en el tipo de sistema de archivos reportado por
    `mount`, en el punto de montaje y en las opciones de montaje; nunca infiere
    el SO a partir de rutas (3.8.5.1.4.3.1) ni declara soporte sin evidencia
    del adaptador (3.8.5.1.4.3.8).
    """
    f = (fstype or "").lower()
    o = (opciones or "").lower()
    mp = (mount_point or "").lower()
    d = (dispositivo or "").lower()

    # 1. Sistemas de archivos virtuales/pseudoficheros del kernel.
    if f in _MACOS_VIRTUAL_FSTYPES:
        return VolumeType.VIRTUAL
    if mp in ("/dev", "/private/var/vm", "/private/var/folders"):
        return VolumeType.VIRTUAL

    # 2. Sistemas de archivos de red.
    if f in _MACOS_NETWORK_FSTYPES:
        return VolumeType.REMOTE
    if "_netdev" in o or "nfs" in o or "cifs" in o:
        return VolumeType.REMOTE

    # 3. Medios extraibles montados bajo /Volumes.
    if f in _MACOS_REMOVABLE_FSTYPES and mp.startswith("/volumes/"):
        return VolumeType.REMOVABLE

    # 4. Sistemas de archivos locales de disco.
    if "local" in o:
        return VolumeType.FIXED
    if f in ("apfs", "hfs", "hfsplus"):
        return VolumeType.FIXED

    return VolumeType.UNKNOWN


def enumerar_volumenes_linux(mounts_path: str = "/proc/mounts") -> list[VolumeInfo]:
    """
    Enumerar en Linux los puntos de montaje disponibles, diferenciando
    sistemas de archivos locales, virtuales, de red y extraibles.

    Lee `/proc/mounts` (ruta configurable para pruebas) usando solo la
    biblioteca estandar, sin dependencias de terceros. Cada línea describe
    un montaje con dispositivo, punto de montaje, tipo de sistema de
    archivos y opciones, que se clasifican en `VolumeType`.

    Devuelve una lista de `VolumeInfo`, una por punto de montaje detectado,
    ordenada por orden de aparicion en `/proc/mounts`. Los campos de
    `VolumeInfo` se rellenan así:
    - `letra`: vacia (Linux no tiene letras de unidad).
    - `ruta_raiz`: el punto de montaje (ej. "/", "/mnt/data").
    - `tipo`: `VolumeType` clasificado (fixed/local, virtual, remote/red,
      removable/extraible o unknown).
    - `disponible`: True mientras el punto de montaje aparezca en /proc/mounts.
    - `sistema_archivos`: el tipo de sistema de archivos reportado.
    - `etiqueta_volumen`: el dispositivo de origen (ej. "/dev/sda1").

    No lee el contenido de los volúmenes ni de archivos personales
    (3.8.5.1.4.1.9). Si `/proc/mounts` no existe (no Linux), devuelve [].
    """
    ruta = Path(mounts_path)
    if not ruta.exists():
        return []

    volumenes: list[VolumeInfo] = []
    try:
        lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    for linea in lineas:
        if not linea.strip() or linea.startswith("#"):
            continue
        partes = linea.split()
        if len(partes) < 3:
            continue
        # Formato /proc/mounts: dispositivo punto_montaje tipo opciones dump pass
        dispositivo = partes[0]
        mount_point = partes[1]
        fstype = partes[2]
        opciones = partes[3] if len(partes) > 3 else ""

        # Ignorar entradas sin punto de montaje valido.
        if not mount_point:
            continue

        tipo = _clasificar_tipo_volumen_linux(dispositivo, fstype, opciones, mount_point)

        volumenes.append(
            VolumeInfo(
                letra="",
                ruta_raiz=mount_point,
                tipo=tipo,
                disponible=True,
                sistema_archivos=fstype,
                etiqueta_volumen=dispositivo,
            )
        )

    return volumenes


# ---------------------------------------------------------------------------
# Enumeracion de volumenes macOS (3.8.5.1.4.3.4)
# ---------------------------------------------------------------------------

def enumerar_volumenes_macos(
    mount_output: Optional[str] = None,
) -> list[VolumeInfo]:
    """
    Enumerar en macOS los volumenes montados, diferenciando volumenes
    locales, de red, virtuales y extraibles.

    Ejecuta el comando `mount` (disponible por defecto en macOS) y parsea
    su salida para obtener dispositivo, punto de montaje, tipo de sistema de
    archivos y opciones de cada volumen montado. Usa solo la biblioteca
    estandar, sin dependencias de terceros.

    Para pruebas, `mount_output` permite inyectar la salida del comando
    `mount` en lugar de ejecutarlo.

    Devuelve una lista de `VolumeInfo`, una por volumen detectado, ordenada
    por orden de aparicion en la salida de `mount`. Los campos de
    `VolumeInfo` se rellenan asi:
    - `letra`: vacia (macOS no tiene letras de unidad).
    - `ruta_raiz`: el punto de montaje (ej. "/", "/Volumes/Datos").
    - `tipo`: `VolumeType` clasificado (fixed/local, virtual, remote/red,
      removable/extraible o unknown).
    - `disponible`: True mientras el volumen aparezca en la salida de `mount`.
    - `sistema_archivos`: el tipo de sistema de archivos reportado.
    - `etiqueta_volumen`: el dispositivo de origen (ej. "/dev/disk1s1").

    No lee el contenido de los volumenes ni de archivos personales
    (3.8.5.1.4.1.9). Si el comando `mount` no esta disponible o falla,
    devuelve [].
    """
    if mount_output is None:
        try:
            resultado = subprocess.run(
                ["mount"],
                capture_output=True,
                text=True,
                check=False,
            )
            mount_output = resultado.stdout
        except (OSError, FileNotFoundError):
            return []

    volumenes: list[VolumeInfo] = []
    for linea in mount_output.splitlines():
        if not linea.strip():
            continue
        # Formato de mount en macOS: dispositivo on punto_montaje (fstype, opciones)
        if " on " not in linea:
            continue
        try:
            dispositivo, resto = linea.split(" on ", 1)
            dispositivo = dispositivo.strip()
            if "(" not in resto or ")" not in resto:
                continue
            mount_point, opciones_part = resto.split("(", 1)
            mount_point = mount_point.strip()
            opciones_part = opciones_part.rsplit(")", 1)[0]
            partes_opciones = [p.strip() for p in opciones_part.split(",")]
            fstype = partes_opciones[0] if partes_opciones else ""
            opciones = ", ".join(partes_opciones[1:]) if len(partes_opciones) > 1 else ""
        except (ValueError, IndexError):
            continue

        if not mount_point:
            continue

        tipo = _clasificar_tipo_volumen_macos(dispositivo, fstype, opciones, mount_point)

        volumenes.append(
            VolumeInfo(
                letra="",
                ruta_raiz=mount_point,
                tipo=tipo,
                disponible=True,
                sistema_archivos=fstype,
                etiqueta_volumen=dispositivo,
            )
        )

    return volumenes


# ---------------------------------------------------------------------------
# Contrato comun de volumen multiplataforma (3.8.5.1.4.3.5)
# ---------------------------------------------------------------------------

@dataclass
class VolumenComun:
    """
    Contrato comun de volumen que no impone conceptos de Windows (letras de
    unidad ni rutas con barra invertida precedidas de letra de unidad) sobre
    otros sistemas operativos.

    Un volumen se identifica por un identificador estable y se accede mediante
    su raiz de acceso, que es platform-agnostica:
    - Windows: identificador = letra de unidad ("C:"), raiz = "C:\\", letra_unidad = "C:".
    - Linux: identificador = punto de montaje ("/", "/mnt/data"), raiz igual,
      letra_unidad = None.
    - macOS: identificador = punto de montaje ("/", "/Volumes/Datos"), raiz igual,
      letra_unidad = None.

    Solo metadatos observados del SO; nunca se lee el contenido del volumen
    (3.8.5.1.4.1.9).
    """

    identificador: str          # identificador estable del volumen (letra en Windows, punto de montaje en otros SO)
    raiz: str                   # ruta de acceso a la raiz del volumen, segun el SO
    tipo: VolumeType            # tipo de volumen observado
    disponible: bool            # True si el volumen esta listo para leer
    sistema_archivos: str = ""
    etiqueta: str = ""
    letra_unidad: Optional[str] = None  # solo tiene sentido en Windows; None en otros SO
    sistema_origen: str = ""    # "Windows", "Linux", "Darwin" o "Desconocido"

    def es_windows(self) -> bool:
        """Devuelve True si el volumen pertenece a un equipo Windows."""
        return self.sistema_origen == "Windows"

    def tiene_letra_unidad(self) -> bool:
        """Devuelve True si el volumen expone una letra de unidad (solo Windows)."""
        return bool(self.letra_unidad)

    def to_dict(self) -> dict:
        """Serializa a diccionario plano."""
        return {
            "identificador": self.identificador,
            "raiz": self.raiz,
            "tipo": self.tipo.value,
            "disponible": self.disponible,
            "sistema_archivos": self.sistema_archivos,
            "etiqueta": self.etiqueta,
            "letra_unidad": self.letra_unidad,
            "sistema_origen": self.sistema_origen,
        }


def volumen_comun_desde_info(
    info: VolumeInfo, sistema_origen: Optional[str] = None
) -> VolumenComun:
    """
    Convierte un `VolumeInfo` específico de plataforma en el contrato comun
    `VolumenComun` sin forzar letras de unidad ni rutas de Windows en otros SO.

    La letra de unidad solo se conserva cuando el origen es Windows o cuando
    el `VolumeInfo` trae una letra no vacia; en Linux y macOS queda `None` y la
    raiz es el punto de montaje. Nunca se inventa una letra de unidad para un
    SO que no la usa (3.8.5.1.4.3.5).
    """
    sistema = sistema_origen or detectar_sistema().sistema_operativo
    letra = info.letra or None
    # La letra de unidad es un concepto Windows: no se conserva en otros SO.
    if sistema != "Windows":
        letra = None
    identificador = letra if letra else info.ruta_raiz
    return VolumenComun(
        identificador=identificador,
        raiz=info.ruta_raiz,
        tipo=info.tipo,
        disponible=info.disponible,
        sistema_archivos=info.sistema_archivos,
        etiqueta=info.etiqueta_volumen,
        letra_unidad=letra if sistema == "Windows" else None,
        sistema_origen=sistema,
    )


def enumerar_volumenes_comun(
    sistema_origen: Optional[str] = None,
) -> list[VolumenComun]:
    """
    Enumerar los volumenes del equipo usando el adaptador del SO real y devolver
    el contrato comun de volumen (sin forzar conceptos de Windows en otros SO).

    `sistema_origen` permite forzar el SO para pruebas ("Windows", "Linux",
    "Darwin"); por defecto se detecta con `detectar_sistema()`.
    """
    sistema = sistema_origen or detectar_sistema().sistema_operativo
    if sistema == "Windows":
        infos = enumerar_volumenes_windows()
    elif sistema == "Linux":
        infos = enumerar_volumenes_linux()
    elif sistema == "Darwin":
        infos = enumerar_volumenes_macos()
    else:
        return []
    return [volumen_comun_desde_info(info, sistema) for info in infos]
