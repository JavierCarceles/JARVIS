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
import os
import platform
import psutil
import subprocess
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


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
    exclusiones_usuario: list[str] = field(default_factory=list)
    """Rutas que el usuario elige excluir del inventario, ademas de las exclusiones tecnicas."""

    def __post_init__(self) -> None:
        if not self.excluded_paths:
            self.excluded_paths = list(DEFAULT_EXCLUDED_PATH_PATTERNS)
        if not self.excluded_mounts:
            self.excluded_mounts = list(DEFAULT_EXCLUDED_MOUNT_PATTERNS)

    def _exclusion_tecnica(self, path: str) -> bool:
        """Devuelve True si `path` coincide con una exclusion tecnica del contrato."""
        return is_excluded_path(path, self.excluded_paths)

    def _exclusion_usuario(self, path: str) -> bool:
        """Devuelve True si `path` coincide con una exclusion elegida por el usuario."""
        return _coincide_alguna_exclusion_ruta(path, self.exclusiones_usuario)

    def should_exclude_path(self, path: str) -> bool:
        """Devuelve True si la ruta debe excluirse segun el contrato.

        Considera tanto las exclusiones tecnicas justificadas como las
        exclusiones de ubicaciones elegidas por el usuario (3.8.5.1.4.8.3).
        """
        return self._exclusion_tecnica(path) or self._exclusion_usuario(path)

    def razon_exclusion(self, path: str) -> Optional[str]:
        """Devuelve el motivo de exclusión de `path` (`exclusion_usuario` o
        `exclusion_tecnica`) o None si la ruta no está excluida."""
        if self._exclusion_usuario(path):
            return "exclusion_usuario"
        if self._exclusion_tecnica(path):
            return "exclusion_tecnica"
        return None

    def agregar_exclusion_usuario(self, ruta: str) -> None:
        """Añade una ubicación elegida por el usuario a las exclusiones del inventario.

        La ruta se normaliza (separadores y mayúsculas según el SO) antes de
        almacenarla; rutas duplicadas no se añaden dos veces.
        """
        normalizada = os.path.normpath(ruta)
        if normalizada not in self.exclusiones_usuario:
            self.exclusiones_usuario.append(normalizada)

    def quitar_exclusion_usuario(self, ruta: str) -> None:
        """Elimina una ubicación de las exclusiones elegidas por el usuario."""
        normalizada = os.path.normpath(ruta)
        self.exclusiones_usuario = [
            entrada for entrada in self.exclusiones_usuario if entrada != normalizada
        ]

    def obtener_exclusiones_usuario(self) -> list[str]:
        """Devuelve una copia de las exclusiones elegidas por el usuario."""
        return list(self.exclusiones_usuario)

    def limpiar_exclusiones_usuario(self) -> None:
        """Elimina todas las exclusiones elegidas por el usuario."""
        self.exclusiones_usuario = []

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
# Limites de recursos para el escaneo (3.8.5.1.4.5.8)
# ---------------------------------------------------------------------------

@dataclass
class LimiteRecursos:
    """
    Limites configurables de recursos para el escaneo de inventario.

    Todos los valores por defecto son None (sin limite): el escaneo usa los
    recursos disponibles sin restriccion artificial. Los limites se configuran
    a partir de mediciones reales del equipo, nunca de umbrales inventados
    (3.8.5.1.4.5.8: "No inventar umbrales fijos sin medir").
    """

    cpu_max_porcentaje: Optional[float] = None
    """Porcentaje máximo de CPU del sistema que el escaneo puede ocupar (0-100). None = sin limite."""

    memoria_max_porcentaje: Optional[float] = None
    """Porcentaje máximo de memoria RAM del sistema que el escaneo puede ocupar (0-100). None = sin limite."""

    disco_uso_max_porcentaje: Optional[float] = None
    """Porcentaje máximo de uso de disco del volumen escaneado (0-100). None = sin limite."""

    concurrencia_maxima: Optional[int] = None
    """Numero máximo de operaciones de escaneo concurrentes. None = sin limite."""

    intervalo_medicion_segundos: float = 1.0
    """Segundos entre mediciones consecutivas de recursos para evitar overhead."""

    def __post_init__(self) -> None:
        for campo, valor in (
            ("cpu_max_porcentaje", self.cpu_max_porcentaje),
            ("memoria_max_porcentaje", self.memoria_max_porcentaje),
            ("disco_uso_max_porcentaje", self.disco_uso_max_porcentaje),
        ):
            if valor is not None and not (0.0 <= valor <= 100.0):
                raise ValueError(
                    f"{campo} debe estar entre 0 y 100, obtuvo {valor!r}"
                )
        if self.concurrencia_maxima is not None and self.concurrencia_maxima < 1:
            raise ValueError(
                f"concurrencia_maxima debe ser >= 1, obtuvo {self.concurrencia_maxima!r}"
            )
        if self.intervalo_medicion_segundos <= 0:
            raise ValueError(
                f"intervalo_medicion_segundos debe ser > 0, obtuvo {self.intervalo_medicion_segundos!r}"
            )


class MedidorRecursosSistema:
    """
    Mide recursos reales del equipo usando psutil (dependencia ya presente
    en el proyecto).

    Provee mediciones de CPU, memoria y disco del sistema real para establecer
    límites de escaneo basados en evidencia, no en umbrales inventados.
    """

    @staticmethod
    def cpu_porcentaje() -> float:
        """Devuelve el porcentaje de CPU actual del sistema (0-100)."""
        return float(psutil.cpu_percent(interval=None))

    @staticmethod
    def memoria_porcentaje() -> float:
        """Devuelve el porcentaje de memoria RAM usada del sistema (0-100)."""
        return float(psutil.virtual_memory().percent)

    @staticmethod
    def disco_uso_porcentaje(ruta: str) -> float:
        """
        Devuelve el porcentaje de uso de disco de la ruta dada (0-100).

        Si la ruta no existe o no se puede consultar, retorna 0.0 para no
        bloquear el escaneo por un error de lectura de disco.
        """
        try:
            return float(psutil.disk_usage(ruta).percent)
        except OSError:
            return 0.0

    @staticmethod
    def medir_todos(ruta_volumen: str) -> dict[str, float]:
        """
        Mide CPU, memoria y disco de una sola vez.

        Retorna un diccionario con claves "cpu", "memoria", "disco".
        """
        return {
            "cpu": MedidorRecursosSistema.cpu_porcentaje(),
            "memoria": MedidorRecursosSistema.memoria_porcentaje(),
            "disco": MedidorRecursosSistema.disco_uso_porcentaje(ruta_volumen),
        }


# ---------------------------------------------------------------------------
# Caducidad y detección de inventario obsoleto (3.8.5.1.4.5.9)
# ---------------------------------------------------------------------------

class EstadoCaducidad(Enum):
    """Estado de caducidad de una entrada de inventario respecto a un umbral de tiempo.

    VIGENTE: la entrada fue comprobada recientemente y se considera válida.
    OBSOLETO: la entrada superó el umbral de antigüedad; sus datos pueden no reflejar el estado real.
    EXPIRADO: la entrada carece de timestamp de comprobación o es claramente inválida.
    DESCONOCIDO: no hay suficiente información para determinar el estado.
    """

    VIGENTE = "vigente"
    OBSOLETO = "obsoleto"
    EXPIRADO = "expirado"
    DESCONOCIDO = "desconocido"


@dataclass
class ConfigCaducidad:
    """Configuración de caducidad para entradas de inventario.

    Todos los valores son opcionales (None = sin límite). Los umbrales se
    configuran a partir de mediciones reales del equipo o necesidades del
    consumidor, nunca por inferencia.
    """

    ttl_segundos: Optional[float] = None
    """Tiempo máximo de vida en segundos desde last_checked_at. None = sin caducidad por tiempo."""

    usar_last_checked: bool = True
    """Si True, usa last_checked_at como referencia de caducidad."""

    usar_modificado: bool = False
    """Si True, también considera modified_at para detectar cambios externos."""

    usar_creado: bool = False
    """Si True, también considera created_at como referencia secundaria."""

    def umbral_efectivo(self) -> Optional[float]:
        """Devuelve el umbral efectivo en segundos o None si no hay caducidad configurada."""
        return self.ttl_segundos


@dataclass
class ResultadoCaducidad:
    """Resultado de la comprobación de caducidad de una entrada de inventario."""

    ruta: str
    """Ruta absoluta de la entrada evaluada."""

    estado: EstadoCaducidad
    """Estado de caducidad determinado."""

    edad_segundos: Optional[float]
    """Edad en segundos desde la última comprobación (None si no hay timestamp)."""

    ultimo_check: Optional[str]
    """Valor de last_checked_at de la entrada."""

    razon: str
    """Explicación legible del estado determinado."""

    es_valido_para_uso: bool
    """True si la entrada se considera válida para usar como destino."""


def edad_segundos_desde_check(entry: InventoryEntry) -> Optional[float]:
    """Calcula la edad en segundos desde last_checked_at de una entrada.

    Retorna None si la entrada no tiene last_checked_at o no se puede parsear.
    Nunca lanza excepción por timestamps inválidos: los trata como desconocidos.
    """
    if not entry.last_checked_at:
        return None
    try:
        ultimo = datetime.fromisoformat(entry.last_checked_at)
        ahora = datetime.now()
        if ultimo.tzinfo is not None:
            ahora = ahora.astimezone()
        return max(0.0, (ahora - ultimo).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def esta_caducado(entry: InventoryEntry, config: Optional[ConfigCaducidad] = None) -> ResultadoCaducidad:
    """Determina si una entrada de inventario está caducada u obsoleta.

    Usa last_checked_at como referencia principal (config.usar_last_checked).
    Si config.ttl_segundos es None, la entrada nunca caduca por tiempo.

    La edad se compara contra el umbral configurado; si se supera, la entrada
    se marca como OBSOLETO. Si no hay timestamp de comprobación, se marca como
    EXPIRADO (no hay evidencia de que siga siendo válida).

    Una ruta histórica nunca se considera válida por sí sola: sin
    last_checked_at reciente o sin revalidación real, el estado es OBSOLETO o
    EXPIRADO.
    """
    cfg = config or ConfigCaducidad()
    ruta = entry.absolute_path
    ultimo_check = entry.last_checked_at or ""
    edad = edad_segundos_desde_check(entry)

    if edad is None:
        return ResultadoCaducidad(
            ruta=ruta,
            estado=EstadoCaducidad.EXPIRADO,
            edad_segundos=None,
            ultimo_check=ultimo_check,
            razon="Sin timestamp de última comprobación (last_checked_at vacío o no parseable).",
            es_valido_para_uso=False,
        )

    umbral = cfg.umbral_efectivo()
    if umbral is None:
        # Sin umbral configurado: no caduca por tiempo, pero sigue necesitando
        # revalidación real antes de usarse como destino.
        return ResultadoCaducidad(
            ruta=ruta,
            estado=EstadoCaducidad.VIGENTE,
            edad_segundos=edad,
            ultimo_check=ultimo_check,
            razon=f"Sin umbral de caducidad configurado. Edad {edad:.1f}s desde última comprobación.",
            es_valido_para_uso=False,
        )

    if edad > umbral:
        return ResultadoCaducidad(
            ruta=ruta,
            estado=EstadoCaducidad.OBSOLETO,
            edad_segundos=edad,
            ultimo_check=ultimo_check,
            razon=f"Edad {edad:.1f}s supera el umbral de {umbral:.1f}s.",
            es_valido_para_uso=False,
        )

    return ResultadoCaducidad(
        ruta=ruta,
        estado=EstadoCaducidad.VIGENTE,
        edad_segundos=edad,
        ultimo_check=ultimo_check,
        razon=f"Edad {edad:.1f}s dentro del umbral de {umbral:.1f}s.",
        es_valido_para_uso=False,
    )


def clasificar_entradas_por_caducidad(
    entradas: list[InventoryEntry], config: Optional[ConfigCaducidad] = None
) -> dict[str, ResultadoCaducidad]:
    """Clasifica una lista de entradas de inventario por su estado de caducidad.

    Devuelve un diccionario claveado por ruta absoluta con el
    ResultadoCaducidad de cada entrada.
    """
    cfg = config or ConfigCaducidad()
    resultados: dict[str, ResultadoCaducidad] = {}
    for entry in entradas:
        resultados[entry.absolute_path] = esta_caducado(entry, cfg)
    return resultados


# ---------------------------------------------------------------------------
# Politica de retencion y limpieza del inventario (3.8.5.1.4.8.6)
# ---------------------------------------------------------------------------


@dataclass
class PoliticaRetencion:
    """
    Politica de retencion y limpieza del inventario persistente.

    Define cuantas generaciones de escaneo conservar por volumen, la edad
    maxima de una generacion y de una entrada, cuantas copias de seguridad
    mantener y los controles de seguridad para no borrar informacion valiosa
    durante un escaneo parcial o en curso.

    Todos los valores son opcionales con sensatos por defecto. Los umbrales
    de edad se configuran a partir de mediciones reales del equipo, nunca de
    umbrales inventados (3.8.5.1.4.5.8).
    """

    max_generaciones_por_volumen: int = 5
    """Numero máximo de generaciones de escaneo (scan_runs) a conservar por
    (machine_id, volumen). None no se aplica: se usa el valor por defecto 5."""

    max_edad_generacion_segundos: Optional[float] = None
    """Edad máxima en segundos de una generacion de escaneo. Las mas antiguas
    se eliminan. None = sin limite por edad."""

    max_edad_entrada_segundos: Optional[float] = None
    """TTL en segundos para entradas de inventario. Las entradas cuyo
    last_checked_at supere este umbral (según ConfigCaducidad) se consideran
    obsoletas y candidatas a limpieza. None = sin caducidad por tiempo."""

    max_backups: int = 3
    """Numero máximo de copias de seguridad (.bak) a conservar junto a la base
    de datos. Las mas antiguas se eliminan."""

    modo_seguro_escaneo_parcial: bool = True
    """Si True, no se elimina ninguna generacion que tenga un escaneo activo
    (has_active_scan) ni se tocan entradas del ultimo escaneo completo del
    volumen, protegiendo la informacion valiosa durante escaneos parciales."""

    crear_backup_antes_limpieza: bool = True
    """Si True, se crea una copia de seguridad antes de cualquier eliminacion
    destructiva de generaciones o entradas obsoletas."""

    def __post_init__(self) -> None:
        if self.max_generaciones_por_volumen < 1:
            raise ValueError(
                f"max_generaciones_por_volumen debe ser >= 1, obtuvo "
                f"{self.max_generaciones_por_volumen!r}"
            )
        if self.max_backups < 1:
            raise ValueError(
                f"max_backups debe ser >= 1, obtuvo {self.max_backups!r}"
            )
        for campo, valor in (
            ("max_edad_generacion_segundos", self.max_edad_generacion_segundos),
            ("max_edad_entrada_segundos", self.max_edad_entrada_segundos),
        ):
            if valor is not None and valor <= 0:
                raise ValueError(
                    f"{campo} debe ser > 0 o None, obtuvo {valor!r}"
                )


@dataclass
class ResultadoLimpieza:
    """Resultado de una operacion de limpieza/retencion del inventario.

    Todos los contadores son reales: generaciones de escaneo eliminadas,
    entradas de archivo eliminadas, copias de seguridad eliminadas y
    advertencias de elementos protegidos por seguridad.
    """

    machine_id: str
    """Equipo al que pertenece el inventario limpiado."""

    generaciones_eliminadas: int = 0
    """Numero de scan_runs (y sus file_entries/application_candidates)
    eliminados por antigüedad o exceso de generaciones."""

    entradas_eliminadas: int = 0
    """Numero de file_entries eliminadas por caducidad/obsolecencia."""

    backups_eliminados: int = 0
    """Numero de copias de seguridad (.bak) eliminadas por retención."""

    backup_creado: Optional[str] = None
    """Ruta de la copia de seguridad creada antes de la limpieza, si procede."""

    generaciones_protegidas: list[str] = field(default_factory=list)
    """scan_ids de generaciones no eliminadas porque estaban activas o eran
    la ultima completa del volumen (modo seguro)."""

    entradas_protegidas: int = 0
    """Numero de entradas no eliminadas porque pertenecen al ultimo escaneo
    completo o no cumplen criterios de obsolecencia."""

    errores: list[str] = field(default_factory=list)
    """Errores no fatales ocurridos durante la limpieza."""

    def resumen(self) -> dict[str, object]:
        """Devuelve un resumen serializable de la limpieza."""
        return {
            "machine_id": self.machine_id,
            "generaciones_eliminadas": self.generaciones_eliminadas,
            "entradas_eliminadas": self.entradas_eliminadas,
            "backups_eliminados": self.backups_eliminados,
            "backup_creado": self.backup_creado,
            "generaciones_protegidas": list(self.generaciones_protegidas),
            "entradas_protegidas": self.entradas_protegidas,
            "errores": list(self.errores),
            "total_eliminado": (
                self.generaciones_eliminadas
                + self.entradas_eliminadas
                + self.backups_eliminados
            ),
        }


@dataclass
class ResultadoValidacionDestino:
    """Resultado de la revalidación de un destino de inventario antes de usarlo.

    Todos los campos son booleans independientes: un destino puede pasar
    algunas comprobaciones y fallar otras. `valido` es True solo si todas
    las comprobaciones críticas pasan.
    """

    ruta: str
    """Ruta absoluta validada."""

    valido: bool
    """True solo si todas las comprobaciones críticas pasaron."""

    existencia_ok: bool
    """True si la ruta existe en el sistema operativo."""

    tipo_ok: bool
    """True si el tipo observado coincide con entry_type de la entrada."""

    volumen_ok: bool
    """True si el volumen de la ruta coincide con el volume de la entrada."""

    identidad_ok: bool
    """True si el machine_id de la entrada coincide con el equipo actual."""

    accesible_ok: bool
    """True si la ruta es accesible (lectura de metadatos sin error)."""

    errores: list[str]
    """Lista de motivos de fallo (vacío si todo pasó)."""

    razon: str
    """Explicación legible del resultado."""


def _volumen_de_ruta(ruta_absoluta: str) -> str:
    """Extrae el identificador de volumen de una ruta absoluta.

    En Windows devuelve la letra de unidad (ej. "C:"). En otros SO devuelve
    el punto de montaje o la raíz del sistema de archivos.
    """
    p = Path(ruta_absoluta)
    if os.name == "nt":
        # Windows: letra de unidad (C:)
        anchura = p.drive
        return anchura if anchura else str(p.anchor)
    # POSIX: punto de montaje (/, /mnt/data, etc.)
    return p.anchor


def validar_destino(
    entry: InventoryEntry,
    machine_id_actual: Optional[str] = None,
) -> ResultadoValidacionDestino:
    """Revalida un destino de inventario antes de usarlo.

    Comprueba, contra el sistema operativo real:
    1. Existencia: la ruta existe (os.path.exists / os.path.islink).
    2. Tipo: el tipo observado coincide con entry.entry_type.
    3. Volumen: el volumen de la ruta coincide con entry.volume.
    4. Identidad: entry.machine_id coincide con el equipo actual.
    5. Accesibilidad: se pueden leer los metadatos de la ruta sin error.

    Una ruta histórica nunca autoriza por sí sola un lanzamiento: incluso si
    la entrada está en el inventario, debe pasar todas estas comprobaciones
    reales antes de usarse como destino.

    Parametros:
    - entry: entrada de inventario a validar.
    - machine_id_actual: identificador del equipo actual; si None, se omite
      la comprobación de identidad (se registra como advertencia en errores).
    """
    ruta = entry.absolute_path
    errores: list[str] = []

    # 1. Existencia
    try:
        existe = os.path.exists(ruta) or os.path.islink(ruta)
    except OSError:
        existe = False
    existencia_ok = bool(existe)
    if not existencia_ok:
        errores.append(f"La ruta no existe en el sistema operativo: {ruta}")

    # 2. Tipo de entrada
    tipo_ok = True
    try:
        if os.path.isdir(ruta) and not os.path.islink(ruta):
            tipo_observado = EntryType.DIRECTORY
        elif os.path.islink(ruta):
            tipo_observado = EntryType.SYMLINK
        elif os.path.isfile(ruta):
            tipo_observado = EntryType.FILE
        else:
            tipo_observado = EntryType.OTHER
        tipo_ok = tipo_observado == entry.entry_type
        if not tipo_ok:
            errores.append(
                f"Tipo no coincide: esperado {entry.entry_type.value}, "
                f"observado {tipo_observado.value}"
            )
    except OSError:
        tipo_ok = False
        errores.append(f"No se pudo determinar el tipo de la ruta: {ruta}")

    # 3. Volumen
    volumen_observado = _volumen_de_ruta(ruta)
    volumen_ok = volumen_observado == entry.volume
    if not volumen_ok:
        errores.append(
            f"Volumen no coincide: esperado {entry.volume}, observado {volumen_observado}"
        )

    # 4. Identidad del equipo
    identidad_ok = True
    if machine_id_actual is not None:
        identidad_ok = entry.machine_id == machine_id_actual
        if not identidad_ok:
            errores.append(
                f"Identidad de equipo no coincide: esperado {machine_id_actual}, "
                f"entrada tiene {entry.machine_id}"
            )
    else:
        identidad_ok = True
        errores.append("machine_id_actual no proporcionado: comprobación de identidad omitida")

    # 5. Accesibilidad
    accesible_ok = True
    try:
        if os.path.isdir(ruta) and not os.path.islink(ruta):
            with os.scandir(ruta) as _:
                pass
        else:
            os.stat(ruta)
    except PermissionError:
        accesible_ok = False
        errores.append(f"Permiso denegado al acceder a la ruta: {ruta}")
    except OSError:
        accesible_ok = False
        errores.append(f"No se puede acceder a la ruta: {ruta}")

    valido = all([existencia_ok, tipo_ok, volumen_ok, identidad_ok, accesible_ok])

    if valido:
        razon = f"Destino válido: {ruta} existe, tipo/volumen/identidad/accesibilidad verificados."
    else:
        razon = f"Destino inválido: {ruta}; {'; '.join(errores) if errores else 'errores no especificados'}"

    return ResultadoValidacionDestino(
        ruta=ruta,
        valido=valido,
        existencia_ok=existencia_ok,
        tipo_ok=tipo_ok,
        volumen_ok=volumen_ok,
        identidad_ok=identidad_ok,
        accesible_ok=accesible_ok,
        errores=errores,
        razon=razon,
    )


def validar_ruta_para_lanzamiento(
    absolute_path: str,
    entry_type: EntryType,
    volume: str,
    machine_id: str,
    machine_id_actual: Optional[str] = None,
) -> ResultadoValidacionDestino:
    """Valida una ruta suelta para lanzamiento, sin requerir una InventoryEntry previa.

    Construye una entrada temporal y aplica validar_destino. Útil para
    comprobar candidatos de aplicación o rutas recuperadas del inventario
    antes de usarlas como destino de lanzamiento.

    Una ruta histórica nunca autoriza por sí sola un lanzamiento: esta
    función exige verificación real en el sistema operativo.
    """
    entrada_temp = InventoryEntry(
        machine_id=machine_id,
        volume=volume,
        absolute_path=absolute_path,
        relative_path="",
        name=Path(absolute_path).name,
        extension=Path(absolute_path).suffix,
        entry_type=entry_type,
        size_bytes=0,
        modified_at="",
        created_at="",
        last_checked_at="",
    )
    return validar_destino(entrada_temp, machine_id_actual)


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


# ---------------------------------------------------------------------------
# Estados de volumen (3.8.5.1.4.3.7)
# ---------------------------------------------------------------------------

class EstadoVolumen(Enum):
    """Estado de un volumen, diferenciando situaciones de acceso y contenido.

    Permite distinguir un volumen simplemente disponible de uno desmontado,
    inaccesible, con permiso denegado, con sistema de archivos no soportado
    o vacio (3.8.5.1.4.3.7).
    """

    DISPONIBLE = "disponible"
    DESMONTADO = "desmontado"
    INACCESIBLE = "inaccesible"
    PERMISO_DENEGADO = "permiso_denegado"
    SISTEMA_ARCHIVOS_NO_SOPORTADO = "sistema_archivos_no_soportado"
    VACIO = "vacio"


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
    estado: EstadoVolumen = EstadoVolumen.DISPONIBLE  # Estado diferenciado del volumen
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
            "estado": self.estado.value,
            "sistema_archivos": self.sistema_archivos,
            "etiqueta": self.etiqueta,
            "letra_unidad": self.letra_unidad,
            "sistema_origen": self.sistema_origen,
        }


def _sistema_archivos_no_soportado(fstype: str) -> bool:
    """Devuelve True si el tipo de sistema de archivos no es soportado para
    inventario (sistemas virtuales, de red o pseudoficheros del kernel).

    No declara no soportado por inferencia: solo los tipos conocidos como
    no inventariables (3.8.5.1.4.3.7).
    """
    f = (fstype or "").lower()
    if not f:
        return False
    return (
        f in _LINUX_VIRTUAL_FSTYPES
        or f in _LINUX_NETWORK_FSTYPES
        or f in _MACOS_VIRTUAL_FSTYPES
        or f in _MACOS_NETWORK_FSTYPES
    )


def _clasificar_acceso_raiz(ruta_raiz: str) -> Optional[EstadoVolumen]:
    """Intenta acceder a la raiz del volumen y clasifica el error, si lo hay.

    Retorna:
    - `EstadoVolumen.PERMISO_DENEGADO` si el SO deniega el acceso por permisos.
    - `EstadoVolumen.INACCESIBLE` si hay otro error de E/S al acceder.
    - `None` si el acceso a la raiz tiene exito.

    Nunca lee el contenido de archivos personales (3.8.5.1.4.1.9).
    """
    try:
        with os.scandir(ruta_raiz) as _:
            pass
        return None
    except PermissionError:
        return EstadoVolumen.PERMISO_DENEGADO
    except OSError:
        return EstadoVolumen.INACCESIBLE


def _volumen_esta_vacio(ruta_raiz: str) -> bool:
    """Detecta si el volumen es accesible pero no tiene entradas.

    Intenta leer la primera entrada del directorio raiz; si no hay ninguna,
    el volumen se considera vacio (3.8.5.1.4.3.7).
    """
    try:
        with os.scandir(ruta_raiz) as entradas:
            try:
                next(entradas)
                return False
            except StopIteration:
                return True
    except OSError:
        return False


def determinar_estado_volumen(
    info: VolumeInfo, sistema_origen: Optional[str] = None
) -> EstadoVolumen:
    """Determina el estado de un volumen diferenciando:

    - `DESMONTADO`: el volumen no esta disponible (sin medio, no montado,
      unidad sin raiz).
    - `PERMISO_DENEGADO`: el volumen existe pero el acceso a la raiz esta
      denegado por permisos.
    - `INACCESIBLE`: el volumen no se puede acceder por error de E/S.
    - `SISTEMA_ARCHIVOS_NO_SOPORTADO`: el tipo de sistema de archivos no
      es inventariable (virtual, de red, pseudofichero).
    - `VACIO`: el volumen es accesible pero no tiene entradas.
    - `DISPONIBLE`: el volumen es accesible y tiene entradas.

    Las comprobaciones se aplican en orden: un volumen no disponible no se
    puede ni siquiera intentar leer, por lo que DESMONTADO tiene prioridad.
    Nunca se lee el contenido de archivos personales (3.8.5.1.4.1.9).
    """
    # 1. No disponible => desmontado (sin medio, no montado, unidad sin raiz)
    if not info.disponible:
        return EstadoVolumen.DESMONTADO

    # 2. Acceso a la raiz: permiso denegado o inaccesible
    error_acceso = _clasificar_acceso_raiz(info.ruta_raiz)
    if error_acceso is not None:
        return error_acceso

    # 3. Sistema de archivos no soportado
    if _sistema_archivos_no_soportado(info.sistema_archivos):
        return EstadoVolumen.SISTEMA_ARCHIVOS_NO_SOPORTADO

    # 4. Volumen vacio (accesible pero sin entradas)
    if _volumen_esta_vacio(info.ruta_raiz):
        return EstadoVolumen.VACIO

    return EstadoVolumen.DISPONIBLE


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
    # Determinar el estado diferenciado del volumen de forma segura;
    # si no se puede comprobar, se asume DISPONIBLE por defecto.
    try:
        estado = determinar_estado_volumen(info, sistema)
    except Exception:
        estado = EstadoVolumen.DISPONIBLE
    return VolumenComun(
        identificador=identificador,
        raiz=info.ruta_raiz,
        tipo=info.tipo,
        disponible=info.disponible,
        estado=estado,
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


# ---------------------------------------------------------------------------
# Identificacion de enlaces y redirecciones del sistema de archivos (3.8.5.1.4.3.6)
# ---------------------------------------------------------------------------

# Atributo de archivo de Windows que indica un reparse point (enlace simbolico,
# junction, punto de montaje de volumen u otro mecanismo de redireccion).
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400

# Etiquetas de reparse point de Windows conocidas (valores del campo
# ReparseTag del REPARSE_DATA_BUFFER).
IO_REPARSE_TAG_SYMLINK = 0xA000000C
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # junction / punto de montaje de volumen


class TipoEnlace(Enum):
    """Tipo de mecanismo de redireccion del sistema de archivos observado."""
    NINGUNO = "ninguno"
    SIMBOLICO = "simbolico"
    JUNCTION = "junction"
    REPARSE_POINT = "reparse_point"
    BIND_MOUNT = "bind_mount"
    OTRO = "otro"


@dataclass
class InfoEnlace:
    """Resultado de la identificacion de un enlace o redireccion.

    `es_enlace` indica si el mecanismo existe. `tipo` clasifica el mecanismo.
    `objetivo` es el destino declarado por el enlace (cuando el SO lo expone).
    `es_ciclico` indica que seguirlo generaria un ciclo dado el conjunto de
    rutas ya visitadas. `seguir` es la decision explicita de si se debe
    atravesar el enlace, segun la politica solicitada.
    """

    es_enlace: bool
    tipo: TipoEnlace
    objetivo: Optional[str]
    es_ciclico: bool
    seguir: bool


def _atributos_archivo_windows(path: str) -> Optional[int]:
    """Devuelve los atributos de archivo de Windows para `path` o None si no
    se pueden obtener (arquitectura no Windows o error de acceso)."""
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        attrs = kernel32.GetFileAttributesW(path)
        if attrs == 0xFFFFFFFF:
            return None
        return int(attrs)
    except (OSError, AttributeError):
        return None


def _etiqueta_reparse_windows(path: str) -> Optional[int]:
    """Lee el `ReparseTag` de un reparse point de Windows mediante
    `DeviceIoControl(FSCTL_GET_REPARSE_POINT)`. Devuelve None si no es un
    reparse point o no se puede leer."""
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            path,
            0,  # GENERIC_READ no necesario para leer el reparse point
            0x00000001 | 0x00000002,  # FILE_SHARE_READ | FILE_SHARE_WRITE
            None,
            3,  # OPEN_EXISTING
            0x00200000,  # FILE_FLAG_OPEN_REPARSE_POINT
            None,
        )
        if handle == -1 or handle is None:
            return None
        try:
            buffer = ctypes.create_string_buffer(1024)
            devuelto = ctypes.c_ulong(0)
            FSCTL_GET_REPARSE_POINT = 0x900A8
            ok = kernel32.DeviceIoControl(
                handle,
                FSCTL_GET_REPARSE_POINT,
                None,
                0,
                buffer,
                ctypes.sizeof(buffer),
                ctypes.byref(devuelto),
                None,
            )
            if not ok:
                return None
            # Los primeros 4 bytes del buffer son el ReparseTag (unsigned long).
            tag = int.from_bytes(buffer.raw[:4], "little", signed=False)
            return tag
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError):
        return None


def detectar_bind_mount_linux(path: str) -> bool:
    """Detecta un bind mount en Linux/Unix.

    Un bind mount hace que el mismo inode (mismo `st_dev` y `st_ino`) sea
    accesible desde dos rutas distintas. Se compara la entrada del `path`
    con la de su directorio padre: si comparten device e inodo, `path` es un
    bind mount (o hard link de directorio, tratandolo de forma equivalente
    para efectos de evitacion de ciclos). Retorna False en no-Linux o error.
    """
    if os.name == "nt" or os.name == "posix" and sys_platform() == "win32":
        return False
    try:
        stat_path = os.stat(path)
        padre = os.path.dirname(path)
        if not padre or padre == path:
            return False
        stat_padre = os.stat(padre)
        return (
            stat_path.st_dev == stat_padre.st_dev
            and stat_path.st_ino == stat_padre.st_ino
        )
    except OSError:
        return False


def sys_platform() -> str:
    """Devuelve el identificador de plataforma de `sys.platform` sin importar
    el modulo sys (evita acoplamiento innecesario en modulos de bajo nivel)."""
    return platform.system()


def detectar_tipo_enlace(path: str) -> InfoEnlace:
    """Identifica si `path` es un enlace simbolico, junction, reparse point o
    bind mount, y declara explicitamente si se debe seguir.

    La decision por defecto es conservadora: no se sigue ningún enlace a menos
    que el llamante lo solicite y el objetivo no genere un ciclo. Un archivo
    o directorio ordinario (sin redireccion) retorna `es_enlace=False` y
    `tipo=NINGUNO`.

    No lee el contenido del archivo destino (privacidad, 3.8.5.1.4.1.9).
    """
    if not os.path.exists(path) and not os.path.islink(path):
        return InfoEnlace(
            es_enlace=False,
            tipo=TipoEnlace.NINGUNO,
            objetivo=None,
            es_ciclico=False,
            seguir=False,
        )

    objetivo: Optional[str] = None
    tipo = TipoEnlace.NINGUNO

    if os.path.islink(path):
        try:
            objetivo = os.readlink(path)
        except OSError:
            objetivo = None
        # En Windows os.path.islink() es True tanto para symlinks como para
        # junctions; se intenta distinguir mediante el ReparseTag.
        if sys_platform() == "Windows":
            tag = _etiqueta_reparse_windows(path)
            if tag == IO_REPARSE_TAG_MOUNT_POINT:
                tipo = TipoEnlace.JUNCTION
            elif tag == IO_REPARSE_TAG_SYMLINK:
                tipo = TipoEnlace.SIMBOLICO
            else:
                tipo = TipoEnlace.SIMBOLICO
        else:
            tipo = TipoEnlace.SIMBOLICO
    elif sys_platform() == "Windows":
        attrs = _atributos_archivo_windows(path)
        if attrs is not None and (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
            tag = _etiqueta_reparse_windows(path)
            if tag == IO_REPARSE_TAG_MOUNT_POINT:
                tipo = TipoEnlace.JUNCTION
            elif tag == IO_REPARSE_TAG_SYMLINK:
                tipo = TipoEnlace.SIMBOLICO
            else:
                tipo = TipoEnlace.REPARSE_POINT
    elif detectar_bind_mount_linux(path):
        tipo = TipoEnlace.BIND_MOUNT

    es_enlace = tipo != TipoEnlace.NINGUNO
    return InfoEnlace(
        es_enlace=es_enlace,
        tipo=tipo,
        objetivo=objetivo,
        es_ciclico=False,  # se calcula en resolver_sin_ciclos con el contexto
        seguir=False,  # decision por defecto conservadora
    )


def _normalizar_para_visitado(path: str) -> str:
    """Devuelve una representación normalizada y absoluta de `path` apta para
    usarse como clave de deteccion de ciclos, respetando la case-sensitividad
    del sistema de archivos subyacente y la normalización Unicode (NFC)."""
    absoluto = os.path.abspath(path)
    normalizado = unicodedata.normalize("NFC", absoluto)
    normalizado = os.path.normpath(normalizado)
    if not _sistema_archivo_case_sensitive():
        normalizado = normalizado.lower()
    return normalizado


def _sistema_archivo_case_sensitive() -> bool:
    """Devuelve True si el sistema de archivos actual distingue mayusculas."""
    try:
        return os.path.normcase("A") != os.path.normcase("a")
    except OSError:
        return True


def _prefix_ruta_larga_windows(path: str) -> str:
    """
    Aplica el prefijo de ruta larga de Windows (`\\\\?\\`) cuando la ruta
    absoluta supera el limite MAX_PATH (260 caracteres) y el SO es Windows.

    En Windows, las rutas con el prefijo `\\\\?\\` pueden alcanzar hasta
    ~32.767 caracteres y evitan el limite historico de 260 de la API Win32.
    Las rutas UNC se transforman a `\\\\?\\UNC\\servidor\\compartido\\...`.
    En sistemas no-Windows se devuelve la ruta sin cambios.

    Nunca se aplica a rutas relativas: solo rutas absolutas ya resueltas.
    """
    if os.name != "nt":
        return path

    absoluto = os.path.abspath(path)

    # Si la ruta ya tiene el prefijo de ruta larga de Windows, no volver a aplicarlo
    # (evitar doble prefijo \\?\\UNC\\?\\... que romperia rutas profundas).
    if absoluto.startswith("\\\\?\\"):
        return absoluto

    if len(absoluto) <= 260:
        return path

    # Rutas UNC: \\servidor\compartido\... -> \\?\UNC\servidor\compartido\...
    if absoluto.startswith("\\\\"):
        sin_barras = absoluto[2:]
        return "\\\\?\\UNC\\" + sin_barras

    # Ruta absoluta normal: C:\... -> \\?\C:\...
    return "\\\\?\\" + absoluto


def _aplicar_prefijo_ruta_larga(ruta: str) -> str:
    """
    Devuelve `ruta` con prefijo de ruta larga de Windows si corresponde.

    Wrapper sobre `_prefix_ruta_larga_windows` para uso claro en los puntos
    de llamada del recorrido (os.scandir, os.stat, etc.). En plataformas
    no-Windows o rutas cortas devuelve la ruta sin cambios.
    """
    return _prefix_ruta_larga_windows(ruta)


def resolver_sin_ciclos(
    path: str,
    visitados: Optional[set[str]] = None,
    seguir_enlaces: bool = False,
) -> tuple[str, Optional[InfoEnlace]]:
    """Resuelve la ruta real de `path` siguiendo enlaces de forma segura.

    Parametros:
    - `path`: ruta a resolver.
    - `visitados`: conjunto de rutas normalizadas ya atravesadas. Si se omite,
      se crea uno nuevo para esta resolucion.
    - `seguir_enlaces`: si True, se atraviesan enlaces simbolicos/junctions
      cuando no generen ciclo; si False, se devuelve el enlace sin atravesar.

    Retorna `(ruta_resuelta, info_enlace_o_none)`. `ruta_resuelta` es la ruta
    canonica despues de atravesar enlaces seguros (o la ruta original si no se
    atraviesa). Si se detecta un ciclo (la ruta ya estaba en `visitados`),
    `ruta_resuelta` es la ruta que cierra el ciclo y `info_enlace` tiene
    `es_ciclico=True`.

    Nunca sigue un enlace dos veces: evita ciclos por enlaces simbolicos,
    junctions, reparse points y bind mounts (3.8.5.1.4.3.6).
    """
    if visitados is None:
        visitados = set()

    actual = path
    info_final: Optional[InfoEnlace] = None
    profundidad = 0
    limite_profundidad = 64  # cota de seguridad contra bucles imprevistos

    while profundidad < limite_profundidad:
        clave = _normalizar_para_visitado(actual)
        if clave in visitados:
            # Ciclo detectado: esta ruta ya fue atravesada.
            info_ciclo = detectar_tipo_enlace(actual)
            return actual, InfoEnlace(
                es_enlace=info_ciclo.es_enlace,
                tipo=info_ciclo.tipo,
                objetivo=info_ciclo.objetivo,
                es_ciclico=True,
                seguir=False,
            )
        visitados.add(clave)

        info = detectar_tipo_enlace(actual)
        info_final = info
        if not info.es_enlace or not seguir_enlaces:
            return actual, info

        # Es un enlace y se solicita atravesarlo: resolver el objetivo.
        if info.objetivo:
            siguiente = os.path.normpath(
                os.path.join(os.path.dirname(actual), info.objetivo)
            )
        else:
            # No se pudo leer el objetivo: no se atraviesa.
            return actual, info

        actual = siguiente
        profundidad += 1

    # Superado el limite de profundidad: tratar como ciclo de seguridad.
    info_final = detectar_tipo_enlace(actual)
    return actual, InfoEnlace(
        es_enlace=info_final.es_enlace,
        tipo=info_final.tipo,
        objetivo=info_final.objetivo,
        es_ciclico=True,
        seguir=False,
    )


def debe_seguir_enlace(
    info: InfoEnlace,
    visitados: set[str],
    politica: str = "conservadora",
) -> bool:
    """Decide explicitamente si se debe seguir un enlace identificado.

    Politicas:
    - `"nunca"`: nunca se sigue un enlace (predeterminado mas seguro).
    - `"conservadora"`: se sigue solo si no es ciclico, el objetivo existe,
      no esta ya visitado y el tipo es reconocido (simbolico o junction).
    - `"siempre"`: se sigue si no es ciclico y el objetivo existe.

    La decision es puramente local y no lee el contenido del destino.
    """
    if politica == "nunca":
        return False
    if info.es_ciclico or not info.es_enlace:
        return False
    if info.tipo not in (
        TipoEnlace.SIMBOLICO,
        TipoEnlace.JUNCTION,
        TipoEnlace.REPARSE_POINT,
        TipoEnlace.BIND_MOUNT,
    ):
        return False
    if info.objetivo is None:
        return False
    if politica == "siempre":
        try:
            return os.path.exists(info.objetivo) or os.path.islink(info.objetivo)
        except OSError:
            return False
    # politica conservadora
    clave_objetivo = _normalizar_para_visitado(info.objetivo)
    if clave_objetivo in visitados:
        return False
    try:
        return os.path.exists(info.objetivo) or os.path.islink(info.objetivo)
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Atributos observados del SO para entradas de inventario (3.8.5.1.4.4.4)
# ---------------------------------------------------------------------------

# Flags de atributos de archivo de Windows (FILE_ATTRIBUTE_*).
_WIN_ATTR_READONLY = 0x00000001
_WIN_ATTR_HIDDEN = 0x00000002
_WIN_ATTR_SYSTEM = 0x00000004
_WIN_ATTR_ARCHIVE = 0x00000020


def _atributos_observados(entrada: os.DirEntry, stat_result) -> list[str]:
    """
    Devuelve los atributos observados del SO para una entrada, sin leer su
    contenido.

    Registra atributos reales (oculto, sistema, solo lectura, archivo) para
    que archivos sin extension, ocultos, del sistema y de formato desconocido
    queden documentados con sus metadatos observados (3.8.5.1.4.4.4). Nunca
    incluye inferencias sobre el tipo de archivo ni sobre lo que hace.

    En Windows usa st_file_attributes del stat (nativos del SO). En POSIX
    detecta oculto por nombre inicial punto y solo lectura por falta de bit de
    escritura del propietario.
    """
    atributos: list[str] = []
    if os.name == "nt":
        attrs = getattr(stat_result, "st_file_attributes", 0)
        if attrs & _WIN_ATTR_HIDDEN:
            atributos.append("hidden")
        if attrs & _WIN_ATTR_SYSTEM:
            atributos.append("system")
        if attrs & _WIN_ATTR_READONLY:
            atributos.append("readonly")
        if attrs & _WIN_ATTR_ARCHIVE:
            atributos.append("archive")
    else:
        nombre = entrada.name
        if nombre.startswith("."):
            atributos.append("hidden")
        if not (stat_result.st_mode & 0o200):  # sin bit de escritura del owner
            atributos.append("readonly")
    return atributos


# ---------------------------------------------------------------------------
# Recorrido iterativo y controlado de directorios por volumen (3.8.5.1.4.4.1)
# ---------------------------------------------------------------------------

class ControlRecorrido(Enum):
    """Decisiones de flujo del recorrido iterativo de un volumen."""
    CONTINUAR = "continuar"
    PAUSAR = "pausar"
    CANCELAR = "cancelar"


@dataclass
class ProgresoRecorrido:
    """Estado de progreso de un recorrido de volumen.

    Se informa tras procesar cada directorio para que el llamante conozca
    el avance sin necesidad de consultar el estado interno del recorrido.
    """

    volumen: str          # identificador del volumen (letra en Windows, punto de montaje en otros SO)
    raiz: str             # ruta de acceso a la raiz del volumen
    entradas_procesadas: int = 0
    directorios_procesados: int = 0
    archivos_procesados: int = 0
    errores: int = 0
    errores_por_categoria: dict[str, int] = field(default_factory=dict)
    exclusiones: int = 0
    cobertura: float = 0.0          # porcentaje de avance (0.0 a 100.0), nunca 100 si quedan rutas pendientes
    entrada_actual: str = ""
    completado: bool = False
    interrumpido: bool = False


@dataclass
class ErrorRecorrido:
    """Error ocurrido al procesar una ruta durante el recorrido de un volumen.

    Los errores se registran por ruta y volumen con una categoria, pero nunca
    abortan el recorrido completo: una excepcion aislada no detiene el escaneo
    de las demas entradas (3.8.5.1.4.4.6, .4.4.7).
    """

    ruta: str             # ruta donde ocurrio el error
    volumen: str          # volumen al que pertenece la ruta
    categoria: str        # "permiso_denegado", "ruta_eliminada", "error_e_s", "error_estado", etc.
    mensaje: str          # mensaje descriptivo del error


class RecorridoVolumen:
    """
    Recorrido iterativo y controlado de directorios por volumen.

    Implementa un recorrido por pila explícita (sin recursión ilimitada)
    sobre un único volumen del sistema de archivos. Captura metadatos de
    cada entrada mediante `InventoryEntry` sin leer el contenido de los
    archivos (privacidad, 3.8.5.1.4.1.9). Maneja errores por ruta
    (permisos denegados, errores de E/S, rutas eliminadas) sin abortar el
    recorrido completo. No lanza búsquedas indiscriminadas: es una operación
    explícita y controlada, no disparada por cada consulta del usuario
    (3.8.5.1.4.4.1).

    Parametros:
    - `volumen`: identificador del volumen.
    - `raiz`: ruta de acceso a la raiz del volumen.
    - `contrato`: `InventoryContract` que define alcance, exclusiones y privacidad.
    - `maquina_id`: identificador local del equipo.
    - `callback_progreso`: función opcional llamada con `ProgresoRecorrido` tras procesar cada directorio.
    - `callback_control`: función opcional llamada antes de procesar cada directorio; si devuelve
      `ControlRecorrido.CANCELAR` el recorrido se interrumpe; si devuelve `PAUSAR` se detiene temporalmente.
    - `seguir_enlaces`: si True, los enlaces simbolicos y junctions no ciclicos se atraviesan segun
      `debe_seguir_enlace` (politica conservadora). Por defecto False: los enlaces se reportan como
      entrada pero no se recorren, preservando el comportamiento seguro de recorrido controlado.
    """

    def __init__(
        self,
        volumen: str,
        raiz: str,
        contrato: InventoryContract,
        maquina_id: str,
        seguir_enlaces: bool = False,
        callback_progreso: Optional[Callable[[ProgresoRecorrido], None]] = None,
        callback_control: Optional[Callable[[], ControlRecorrido]] = None,
        limite_recursos: Optional[LimiteRecursos] = None,
        medidor_recursos: Optional[MedidorRecursosSistema] = None,
    ) -> None:
        self.volumen = volumen
        self.raiz = _aplicar_prefijo_ruta_larga(os.path.abspath(raiz))
        self.contrato = contrato
        self.maquina_id = maquina_id
        self._seguir_enlaces = seguir_enlaces
        self.callback_progreso = callback_progreso
        self.callback_control = callback_control
        self.limite_recursos = limite_recursos
        self._medidor = medidor_recursos or MedidorRecursosSistema()
        self._ultima_medicion = 0.0
        self._recursos_ultimos: dict[str, float] = {}
        self._concurrencia_actual = 0
        self._progreso = ProgresoRecorrido(volumen=volumen, raiz=self.raiz)
        self._errores: list[ErrorRecorrido] = []
        self._visitados: set[str] = set()
        self._interrumpido = False
        self._entradas_emitidas: list[InventoryEntry] = []

    @property
    def progreso(self) -> ProgresoRecorrido:
        """Devuelve el progreso actual del recorrido."""
        return self._progreso

    @property
    def errores(self) -> list[ErrorRecorrido]:
        """Devuelve una copia de los errores acumulados durante el recorrido."""
        return list(self._errores)

    @property
    def errores_por_categoria(self) -> dict[str, int]:
        """Devuelve una copia del conteo de errores agrupado por categoría."""
        return dict(self._progreso.errores_por_categoria)

    @property
    def entradas_validas(self) -> list[InventoryEntry]:
        """Devuelve una copia de las entradas emitidas hasta el momento.

        Representa el ultimo inventario valido: las entradas que se
        emitieron correctamente antes de una interrupcion o antes de
        completar el recorrido. Si el recorrido se interrumpe, estas
        entradas se conservan y no se descartan (3.8.5.1.4.4.9).
        """
        return list(self._entradas_emitidas)

    @property
    def ejecucion_parcial(self) -> bool:
        """Devuelve True si la ultima ejecucion de `recorrer()` fue
        interrumpida (cancelada o pausada) antes de completar.

        Una ejecucion parcial significa que el volumen o subarbol no
        termino de escanearse; las entradas ya emitidas constituyen el
        ultimo inventario valido y no se deben marcar sus archivos
        como eliminados (3.8.5.1.4.4.9).
        """
        return self._progreso.interrumpido

    def _clave_directorio(self, path: str) -> str:
        """Identificador canonico de visita para un directorio.

        Combina la ruta real resuelta (symlinks y junctions) con la identidad
        de inodo en POSIX, de modo que dos rutas distintas que apuntan al
        mismo objeto del sistema de archivos (enlace simbolico, junction,
        reparse point o bind mount) generen la misma clave y no se recorran
        dos veces (3.8.5.1.4.4.2).
        """
        try:
            real = os.path.realpath(path)
        except OSError:
            real = path
        clave = self._normalizar_visitado(real)
        if os.name != "nt":
            try:
                st = os.stat(real)
                clave += f"|{st.st_dev}:{st.st_ino}"
            except OSError:
                pass
        return clave

    def _considerar_directorio_para_pila(self, ruta: str, pila: list[str]) -> None:
        """Agrega `ruta` a la pila de recorrido solo si aun no fue visitada.

        Usa el identificador canonico de visita, por lo que descarta
        silenciosamente ciclos, duplicados por punto de montaje y recorridos
        repetidos de enlaces (3.8.5.1.4.4.2). Se registra la clave al apilar
        para que la pila nunca contenga el mismo directorio dos veces.
        """
        clave = self._clave_directorio(ruta)
        if clave in self._visitados:
            return
        self._visitados.add(clave)
        pila.append(ruta)

    def _registrar_error(self, ruta: str, categoria: str, mensaje: str) -> None:
        """Añade un error al registro sin abortar el recorrido.

        Registra el error por ruta y volumen con su categoría, e incrementa
        el contador total y el contador agregado por categoría, de modo que
        una excepción aislada no detiene el escaneo pero queda contabilizada
        (3.8.5.1.4.4.7).

        El log registra solo el conteo agregado por categoría y la ruta
        acortada mediante safe_log_path, nunca el listado completo de rutas
        con error (3.8.5.1.4.8.5).
        """
        self._errores.append(
            ErrorRecorrido(
                ruta=ruta,
                volumen=self.volumen,
                categoria=categoria,
                mensaje=mensaje,
            )
        )
        self._progreso.errores = len(self._errores)
        self._progreso.errores_por_categoria[categoria] = (
            self._progreso.errores_por_categoria.get(categoria, 0) + 1
        )
        logger.warning(
            "Error de recorrido [%s] en volumen %s (categoria=%s, total_errores=%d, ruta=%s)",
            categoria,
            self.volumen,
            categoria,
            self._progreso.errores,
            safe_log_path(ruta),
        )

    def _calcular_cobertura(self) -> float:
        """Calcula el porcentaje de cobertura del recorrido.

        La cobertura avanza a medida que se procesan directorios y nunca
        alcanza el 100% mientras queden directorios pendientes en la pila
        (rutas relevantes sin inspeccionar). Cuando la pila esta vacia y el
        recorrido finalizo, la cobertura es 100%.
        """
        pila = getattr(self, "_pila", [])
        pendientes = len(pila)
        total = self._progreso.directorios_procesados + pendientes
        if total == 0:
            return 0.0
        return round(self._progreso.directorios_procesados / total * 100.0, 2)

    def _normalizar_visitado(self, path: str) -> str:
        """Devuelve la representación normalizada de `path` para el conjunto de visitados."""
        absoluto = os.path.abspath(path)
        normalizado = unicodedata.normalize("NFC", absoluto)
        normalizado = os.path.normpath(normalizado)
        if not _sistema_archivo_case_sensitive():
            normalizado = normalizado.lower()
        return normalizado

    def _debe_excluir(self, path: str) -> bool:
        """Devuelve True si la ruta debe excluirse según el contrato de inventario."""
        return self.contrato.should_exclude_path(path)

    def _timestamp_seguro(self, valor: float) -> str:
        """Convierte un timestamp de estadísticas del SO a ISO 8601 de forma segura."""
        try:
            return datetime.fromtimestamp(valor).isoformat()
        except (OSError, ValueError, OverflowError):
            return ""

    def _crear_entrada(self, entrada: os.DirEntry, ruta_absoluta: str) -> Optional[InventoryEntry]:
        """Crea un `InventoryEntry` a partir de una entrada de directorio, sin leer su contenido.

        Solo metadatos observados por el SO. Si la entrada no se puede leer porque
        esta bloqueada, fue eliminada o cambio durante el recorrido
        (stat, is_dir, is_symlink o is_file fallan), se registra el error por ruta
        con categoria `error_estado` y se retorna None para que el recorrido continúe
        con la siguiente entrada sin abortar (3.8.5.1.4.4.6).
        """
        try:
            stat = entrada.stat(follow_symlinks=False)
            nombre = entrada.name
            extension = os.path.splitext(nombre)[1]

            # Tipo de entrada observado directamente del SO, sin inferencias.
            if entrada.is_dir(follow_symlinks=False):
                tipo_entrada = EntryType.DIRECTORY
            elif entrada.is_symlink():
                tipo_entrada = EntryType.SYMLINK
            elif entrada.is_file(follow_symlinks=False):
                tipo_entrada = EntryType.FILE
            else:
                tipo_entrada = EntryType.OTHER

            ahora = datetime.now().isoformat()
            try:
                relativa = os.path.relpath(ruta_absoluta, self.raiz)
            except ValueError:
                relativa = nombre

            razon = self.contrato.razon_exclusion(ruta_absoluta)
            excluida = razon is not None
            atributos = _atributos_observados(entrada, stat)

            return InventoryEntry(
            machine_id=self.maquina_id,
            volume=self.volumen,
            absolute_path=ruta_absoluta,
            relative_path=relativa,
            name=nombre,
            extension=extension,
            entry_type=tipo_entrada,
            size_bytes=int(stat.st_size) if tipo_entrada == EntryType.FILE else 0,
            modified_at=self._timestamp_seguro(stat.st_mtime),
            created_at=self._timestamp_seguro(stat.st_ctime),
            accessed_at=self._timestamp_seguro(stat.st_atime),
            attributes=atributos,
            excluded=excluida,
            exclusion_reason=razon,
            source="filesystem_scan",
            last_checked_at=ahora,
        )
        except OSError as exc:
            self._registrar_error(ruta_absoluta, "error_estado", f"No se pudieron leer los metadatos de la entrada durante el recorrido: {exc}")
            return None

    def _recursos_dentro_de_limites(self) -> tuple[bool, str]:
        """
        Comprueba si los recursos actuales estan dentro de los límites configurados.

        Mide CPU, memoria y disco solo si ha pasado el intervalo de medicion
        configurado, para evitar overhead por mediciones demasiado frecuentes.

        Retorna (dentro_de_limites, motivo). Si dentro_de_limites es False,
        el motivo explica qué límite se excedió.
        """
        if self.limite_recursos is None:
            return True, ""

        ahora = time.time()
        if (
            ahora - self._ultima_medicion
            < self.limite_recursos.intervalo_medicion_segundos
        ):
            # Todavía no toca medir: usar la última medición conocida.
            if not self._recursos_ultimos:
                return True, ""
            recursos = self._recursos_ultimos
        else:
            self._ultima_medicion = ahora
            self._recursos_ultimos = self._medidor.medir_todos(self.raiz)
            recursos = self._recursos_ultimos

        limites = self.limite_recursos

        if (
            limites.cpu_max_porcentaje is not None
            and recursos["cpu"] > limites.cpu_max_porcentaje
        ):
            return (
                False,
                f"CPU {recursos['cpu']:.1f}% > límite {limites.cpu_max_porcentaje}%",
            )
        if (
            limites.memoria_max_porcentaje is not None
            and recursos["memoria"] > limites.memoria_max_porcentaje
        ):
            return (
                False,
                f"Memoria {recursos['memoria']:.1f}% > límite {limites.memoria_max_porcentaje}%",
            )
        if (
            limites.disco_uso_max_porcentaje is not None
            and recursos["disco"] > limites.disco_uso_max_porcentaje
        ):
            return (
                False,
                f"Disco {recursos['disco']:.1f}% > límite {limites.disco_uso_max_porcentaje}%",
            )
        if (
            limites.concurrencia_maxima is not None
            and self._concurrencia_actual >= limites.concurrencia_maxima
        ):
            return (
                False,
                f"Concurrencia {self._concurrencia_actual} >= límite {limites.concurrencia_maxima}",
            )

        return True, ""

    def recorrer(self) -> Iterator[InventoryEntry]:
        """
        Recorre iterativamente el volumen emitiendo `InventoryEntry` por cada entrada accesible.

        Usa una pila explícita en lugar de recursión, de modo que no hay
        riesgo de desbordamiento de pila en árboles de directorios profundos
        (evita recursión sin límites). Los errores por ruta se registran y
        el recorrido continúa con la siguiente entrada.

        El conjunto de visitados usa identificadores canonicos por directorio
        (ruta real resuelta y, en POSIX, identidad de dispositivo/inodo), por
        lo que se evitan ciclos, duplicados por punto de montaje y
        recorridos repetidos de enlaces. Las claves se registran al apilar,
        de modo que la pila nunca contiene el mismo directorio dos veces.

        `seguir_enlaces` controla si los enlaces simbolicos/junctions no
        ciclicos se atraviesan (politica conservadora); por defecto no se
        recorren.

        `limite_recursos` (si se configura) limita CPU, memoria, disco y
        concurrencia del escaneo usando mediciones reales del equipo. Antes
        de procesar cada directorio se comprueban los límites y, si algún
        recurso está por encima del umbral configurado, se espera brevemente
        y se reintenta (throttling), sin abortar el recorrido ni perder las
        entradas ya emitidas.

        Genera:
        - `InventoryEntry` para cada archivo, directorio, enlace u otro elemento accesible.
        """
        logger.info(
            "Inicio de recorrido de volumen=%s raiz=%s modo=seguir_enlaces=%s",
            self.volumen,
            safe_log_path(self.raiz),
            self._seguir_enlaces,
        )
        self._progreso = ProgresoRecorrido(volumen=self.volumen, raiz=self.raiz)
        self._errores = []
        self._visitados = set()
        self._interrumpido = False
        self._entradas_emitidas = []

        # Semilla del conjunto de visitados con la raiz: se visita exactamente
        # una vez y nunca se vuelve a procesar.
        self._visitados.add(self._clave_directorio(self.raiz))
        self._pila: list[str] = [self.raiz]

        while self._pila:
            # Comprobar control de flujo (pausa/cancelar) antes de cada directorio.
            if self.callback_control is not None:
                decision = self.callback_control()
                if decision == ControlRecorrido.CANCELAR:
                    self._progreso.interrumpido = True
                    self._progreso.completado = False
                    self._progreso.cobertura = self._calcular_cobertura()
                    if self.callback_progreso is not None:
                        self.callback_progreso(self._progreso)
                    return
                if decision == ControlRecorrido.PAUSAR:
                    self._progreso.interrumpido = True
                    self._progreso.completado = False
                    self._progreso.cobertura = self._calcular_cobertura()
                    if self.callback_progreso is not None:
                        self.callback_progreso(self._progreso)
                    return

            # Comprobar límites de recursos antes de procesar el directorio.
            # Si algún recurso está por encima del umbral, se espera brevemente
            # y se reintenta (throttling) sin abortar el recorrido.
            dentro, motivo = self._recursos_dentro_de_limites()
            if not dentro:
                time.sleep(self.limite_recursos.intervalo_medicion_segundos)
                continue

            self._concurrencia_actual += 1
            directorio_actual = self._pila.pop()

            self._progreso.entrada_actual = directorio_actual
            self._progreso.directorios_procesados += 1

            try:
                ruta_scandir = _aplicar_prefijo_ruta_larga(directorio_actual)
                with os.scandir(ruta_scandir) as iterator:
                    for entrada in iterator:
                        ruta_absoluta = entrada.path

                        # Respetar exclusiones del contrato de inventario.
                        if self._debe_excluir(ruta_absoluta):
                            self._progreso.exclusiones += 1
                            continue

                        entry = self._crear_entrada(entrada, ruta_absoluta)
                        if entry is None:
                            continue

                        if entry.excluded:
                            self._progreso.exclusiones += 1
                            continue

                        self._progreso.entradas_procesadas += 1

                        if entry.entry_type == EntryType.FILE:
                            self._progreso.archivos_procesados += 1
                        elif entry.entry_type == EntryType.DIRECTORY:
                            # Directorio real: apilar si su identificador de
                            # visita aun no fue registrado.
                            self._considerar_directorio_para_pila(ruta_absoluta, self._pila)
                        elif (
                            entry.entry_type == EntryType.SYMLINK
                            and self._seguir_enlaces
                        ):
                            # Enlace simbolico/junction: atravesar solo si la
                            # politica lo permite y su objetivo no genera ciclo
                            # ni repite una visita ya registrada.
                            info_enlace = detectar_tipo_enlace(ruta_absoluta)
                            if debe_seguir_enlace(
                                info_enlace, self._visitados, "conservadora"
                            ):
                                self._considerar_directorio_para_pila(
                                    ruta_absoluta, self._pila
                                )

                        self._entradas_emitidas.append(entry)
                        yield entry

            except PermissionError as exc:
                self._registrar_error(directorio_actual, "permiso_denegado", str(exc))
                continue
            except FileNotFoundError as exc:
                self._registrar_error(directorio_actual, "ruta_eliminada", str(exc))
                continue
            except OSError as exc:
                self._registrar_error(directorio_actual, "error_e_s", str(exc))
                continue
            finally:
                self._concurrencia_actual -= 1

            # Notificar progreso tras procesar cada directorio.
            if self.callback_progreso is not None:
                self._progreso.cobertura = self._calcular_cobertura()
                self.callback_progreso(self._progreso)

            # Resumen periodico de progreso (cada 50 directorios) sin listar
            # rutas ni nombres individuales (3.8.5.1.4.8.5).
            if self._progreso.directorios_procesados % 50 == 0:
                logger.info(
                    "Progreso recorrido volumen=%s directorios=%d entradas=%d archivos=%d directorios=%d errores=%d exclusiones=%d cobertura=%.2f%%",
                    self.volumen,
                    self._progreso.directorios_procesados,
                    self._progreso.entradas_procesadas,
                    self._progreso.archivos_procesados,
                    self._progreso.directorios_procesados,
                    self._progreso.errores,
                    self._progreso.exclusiones,
                    self._progreso.cobertura,
                )

        self._progreso.completado = True
        self._progreso.interrumpido = False
        self._progreso.cobertura = 100.0
        if self.callback_progreso is not None:
            self.callback_progreso(self._progreso)

        logger.info(
            "Fin de recorrido volumen=%s directorios=%d entradas=%d archivos=%d errores=%d exclusiones=%d cobertura=%.2f%% interrumpido=%s",
            self.volumen,
            self._progreso.directorios_procesados,
            self._progreso.entradas_procesadas,
            self._progreso.archivos_procesados,
            self._progreso.errores,
            self._progreso.exclusiones,
            self._progreso.cobertura,
            self._progreso.interrumpido,
        )


# ---------------------------------------------------------------------------
# Primer inventario del equipo: cuándo se ejecuta, alcance y progreso sin
# bloqueo del arranque ni de la conversación de JARVIS (3.8.5.1.4.8.1).
# ---------------------------------------------------------------------------

class PrimerInventarioYaEnEjecucionError(Exception):
    """Ya hay una ejecución de primer inventario en curso para este equipo."""


class EstadoPrimerInventario(Enum):
    """Estado del ciclo de vida del primer inventario de un equipo."""

    PENDIENTE = "pendiente"        # No existe ningún escaneo previo registrado.
    EJECUTANDOSE = "ejecutandose"  # Ejecución en curso en segundo plano.
    COMPLETADO = "completado"      # Al menos un escaneo previo finalizó con éxito.
    INTERRUMPIDO = "interrumpido"  # La última ejecución se interrumpió (pausa/cancelar/error).


@dataclass
class AlcanceInventario:
    """Informe de alcance del primer inventario (qué se escaneará y por qué)."""

    machine_id: str
    sistema_operativo: str
    modo: str                      # "completo" (SCAN_MODE_FULL del almacenamiento).
    volumenes_a_escanear: list[VolumeInfo]
    total_volumenes: int
    volumenes_excluidos: list[str]
    exclusiones_rutas: list[str]
    incluir_ocultos: bool
    incluir_sistema: bool
    leer_contenido_archivos: bool  # Siempre False por privacidad (3.8.5.1.4.1.9).
    es_primer_inventario: bool
    motivo: str                    # Por qué se ejecuta o no el primer inventario.
    generado_en: str


@dataclass
class ProgresoInventario:
    """Progreso agregado del primer inventario en todos los volúmenes."""

    machine_id: str
    estado: EstadoPrimerInventario
    volumen_actual: str
    volumenes_completados: int
    total_volumenes: int
    entradas_procesadas: int
    directorios_procesados: int
    archivos_procesados: int
    errores: int
    errores_por_categoria: dict[str, int]
    cobertura_global: float        # 0.0 - 100.0.
    entrada_actual: str
    completado: bool
    interrumpido: bool
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    scan_ids: list[str] = field(default_factory=list)


class EjecucionPrimerInventario:
    """Manejo de una ejecución de primer inventario en segundo plano.

    Se devuelve inmediatamente al llamante sin bloquear el arranque ni la
    conversación de JARVIS. Permite consultar el progreso, solicitar pausa /
    cancelación y esperar la finalización. El hilo de escaneo es daemon.
    """

    def __init__(
        self,
        machine_id: str,
        total_volumenes: int,
        callback_progreso: Optional[Callable[[ProgresoInventario], None]] = None,
    ) -> None:
        self._machine_id = machine_id
        self._total_volumenes = max(0, int(total_volumenes))
        self._callback_progreso = callback_progreso
        self._lock = threading.Lock()
        self._solicitar_pausa = False
        self._solicitar_cancelar = False
        self._finalizado = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self._resultado: Optional[dict] = None
        started = datetime.now().isoformat()
        self._progreso = ProgresoInventario(
            machine_id=machine_id,
            estado=EstadoPrimerInventario.EJECUTANDOSE,
            volumen_actual="",
            volumenes_completados=0,
            total_volumenes=self._total_volumenes,
            entradas_procesadas=0,
            directorios_procesados=0,
            archivos_procesados=0,
            errores=0,
            errores_por_categoria={},
            cobertura_global=0.0,
            entrada_actual="",
            completado=False,
            interrumpido=False,
            started_at=started,
        )

    @property
    def hilo(self) -> Optional[threading.Thread]:
        return self._hilo

    @hilo.setter
    def hilo(self, valor: Optional[threading.Thread]) -> None:
        self._hilo = valor

    @property
    def progreso(self) -> ProgresoInventario:
        """Devuelve una copia del progreso actual."""
        with self._lock:
            p = self._progreso
            return ProgresoInventario(
                machine_id=p.machine_id,
                estado=p.estado,
                volumen_actual=p.volumen_actual,
                volumenes_completados=p.volumenes_completados,
                total_volumenes=p.total_volumenes,
                entradas_procesadas=p.entradas_procesadas,
                directorios_procesados=p.directorios_procesados,
                archivos_procesados=p.archivos_procesados,
                errores=p.errores,
                errores_por_categoria=dict(p.errores_por_categoria),
                cobertura_global=p.cobertura_global,
                entrada_actual=p.entrada_actual,
                completado=p.completado,
                interrumpido=p.interrumpido,
                started_at=p.started_at,
                finished_at=p.finished_at,
                scan_ids=list(p.scan_ids),
            )

    @property
    def esta_en_ejecucion(self) -> bool:
        """True mientras el hilo de escaneo esté vivo y no finalizado."""
        if self._finalizado.is_set():
            return False
        hilo = self._hilo
        return hilo is not None and hilo.is_alive()

    @property
    def finalizado(self) -> bool:
        return self._finalizado.is_set()

    @property
    def solicitado_pausa(self) -> bool:
        with self._lock:
            return self._solicitar_pausa

    @property
    def solicitado_cancelar(self) -> bool:
        with self._lock:
            return self._solicitar_cancelar

    def solicitar_pausa(self) -> None:
        """Pide pausar el escaneo al procesar el siguiente directorio."""
        with self._lock:
            if not self._solicitar_cancelar:
                self._solicitar_pausa = True

    def solicitar_reanudar(self) -> None:
        """Reanuda un escaneo pausado."""
        with self._lock:
            self._solicitar_pausa = False

    def solicitar_cancelar(self) -> None:
        """Pide cancelar el escaneo lo antes posible."""
        with self._lock:
            self._solicitar_cancelar = True
            self._solicitar_pausa = False

    def control(self) -> ControlRecorrido:
        """Devuelve la decisión de control para `RecorridoVolumen` (pausa/cancelar)."""
        with self._lock:
            if self._solicitar_cancelar:
                return ControlRecorrido.CANCELAR
            if self._solicitar_pausa:
                return ControlRecorrido.PAUSAR
        return ControlRecorrido.CONTINUAR

    def esperar(self, timeout: Optional[float] = None) -> bool:
        """Espera a que finalice la ejecución. Retorna True si finalizó."""
        return self._finalizado.wait(timeout)

    def resultado(self) -> Optional[dict]:
        """Devuelve el resumen de la ejecución una vez finalizada."""
        with self._lock:
            return None if self._resultado is None else dict(self._resultado)

    def _snapshot(self) -> ProgresoInventario:
        p = self._progreso
        return ProgresoInventario(
            machine_id=p.machine_id,
            estado=p.estado,
            volumen_actual=p.volumen_actual,
            volumenes_completados=p.volumenes_completados,
            total_volumenes=p.total_volumenes,
            entradas_procesadas=p.entradas_procesadas,
            directorios_procesados=p.directorios_procesados,
            archivos_procesados=p.archivos_procesados,
            errores=p.errores,
            errores_por_categoria=dict(p.errores_por_categoria),
            cobertura_global=p.cobertura_global,
            entrada_actual=p.entrada_actual,
            completado=p.completado,
            interrumpido=p.interrumpido,
            started_at=p.started_at,
            finished_at=p.finished_at,
            scan_ids=list(p.scan_ids),
        )

    def _notificar_progreso(self, **cambios) -> None:
        """Aplica cambios al progreso e invoca el callback de progreso.

        El callback nunca debe interrumpir el escaneo: si falla, se ignora.
        """
        with self._lock:
            p = self._progreso
            for clave, valor in cambios.items():
                if hasattr(p, clave):
                    setattr(p, clave, valor)
            snapshot = self._snapshot()
        if self._callback_progreso is not None:
            try:
                self._callback_progreso(snapshot)
            except Exception:
                pass

    def _finalizar(self, estado: EstadoPrimerInventario, resultado: dict) -> None:
        with self._lock:
            self._progreso.estado = estado
            self._progreso.completado = estado == EstadoPrimerInventario.COMPLETADO
            self._progreso.interrumpido = estado == EstadoPrimerInventario.INTERRUMPIDO
            self._progreso.finished_at = datetime.now().isoformat()
            self._resultado = resultado
            snapshot = self._snapshot()
        self._finalizado.set()
        if self._callback_progreso is not None:
            try:
                self._callback_progreso(snapshot)
            except Exception:
                pass


class GestorPrimerInventario:
    """
    Gestiona el primer inventario del equipo (unidad 3.8.5.1.4.8.1).

    Responsabilidades:
    1. Decidir si el primer inventario debe ejecutarse: se ejecuta cuando no
       existe ningún escaneo previo con resultado "ok" para este equipo en
       el almacenamiento.
    2. Informar el alcance del inventario (volúmenes a escanear, exclusiones,
       contrato de privacidad) sin ejecutarlo.
    3. Ejecutar el primer inventario en segundo plano (hilo daemon) usando
       `RecorridoVolumen` por volumen y `SystemInventoryStorage` para la
       persistencia, sin bloquear el arranque ni la conversación de JARVIS.

    `storage` es una instancia de `SystemInventoryStorage` inyectada para
    evitar la dependencia circular entre `system_inventory` y
    `system_inventory_storage`.
    """

    def __init__(
        self,
        machine_id: str,
        storage: Any,
        contrato: Optional[InventoryContract] = None,
        medidor: Optional[MedidorRecursosSistema] = None,
        tamano_lote_entradas: int = 500,
    ) -> None:
        self.machine_id = machine_id
        self.storage = storage
        self.contrato = contrato or default_contract()
        self.medidor = medidor or MedidorRecursosSistema()
        self.tamano_lote_entradas = max(1, int(tamano_lote_entradas))
        self._ejecucion_actual: Optional[EjecucionPrimerInventario] = None
        self._lock = threading.Lock()

    def debe_ejecutar_primer_inventario(self) -> tuple[bool, str]:
        """Decide si debe ejecutarse el primer inventario.

        Retorna `(True, motivo)` cuando no existe ningún `scan_run` con
        resultado `"ok"` para este equipo en el almacenamiento. Retorna
        `(False, motivo)` cuando ya existe al menos un inventario previo
        completado.
        """
        try:
            ultimo = self.storage.get_latest_scan(self.machine_id)
        except Exception:
            ultimo = None
        if ultimo is None:
            return (
                True,
                "No existe ningún escaneo previo registrado para este equipo.",
            )
        resultado = str(ultimo.get("result", "") or "")
        scan_id = ultimo.get("scan_id")
        if resultado == "ok":
            return (
                False,
                f"Ya existe un inventario previo completado (scan {scan_id}).",
            )
        return (
            True,
            f"El último escaneo previo finalizó con resultado '{resultado}' "
            f"o sin finalizar (scan {scan_id}); se ejecuta el primer inventario.",
        )

    def reportar_alcance(self) -> AlcanceInventario:
        """Informa el alcance del primer inventario sin ejecutarlo.

        Enumera los volúmenes reales del sistema operativo, aplica las
        exclusiones del contrato de inventario y devuelve qué volúmenes se
        escanearían, cuántos, cuáles quedan excluidos y por qué.
        """
        debe, motivo = self.debe_ejecutar_primer_inventario()
        sistema = detectar_sistema()
        volumenes_reales = self._volumenes_reales(sistema)
        a_escanear: list[VolumeInfo] = []
        excluidos: list[str] = []
        for volumen in volumenes_reales:
            raiz = volumen.ruta_raiz or volumen.letra
            if not volumen.disponible:
                excluidos.append(raiz)
                continue
            if self.contrato.should_exclude_mount(raiz):
                excluidos.append(raiz)
                continue
            a_escanear.append(volumen)
        return AlcanceInventario(
            machine_id=self.machine_id,
            sistema_operativo=sistema.sistema_operativo,
            modo="completo",
            volumenes_a_escanear=a_escanear,
            total_volumenes=len(a_escanear),
            volumenes_excluidos=excluidos,
            exclusiones_rutas=list(self.contrato.excluded_paths),
            incluir_ocultos=self.contrato.include_hidden,
            incluir_sistema=self.contrato.include_system,
            leer_contenido_archivos=self.contrato.read_file_content,
            es_primer_inventario=debe,
            motivo=motivo,
            generado_en=datetime.now().isoformat(),
        )

    def ejecutar_primera_vez(
        self,
        callback_progreso: Optional[Callable[[ProgresoInventario], None]] = None,
        volumenes: Optional[list[VolumeInfo]] = None,
    ) -> EjecucionPrimerInventario:
        """
        Ejecuta el primer inventario en segundo plano y devuelve el manejo
        inmediatamente (no bloqueante).

        `volumenes` permite inyectar la lista de volúmenes a escanear para
        pruebas; si no se proporciona, se enumeran los volúmenes reales del
        sistema operativo.
        """
        with self._lock:
            if (
                self._ejecucion_actual is not None
                and self._ejecucion_actual.esta_en_ejecucion
            ):
                raise PrimerInventarioYaEnEjecucionError(
                    "Ya hay una ejecución de primer inventario en curso para "
                    f"el equipo {self.machine_id!r}."
                )
            debe, motivo = self.debe_ejecutar_primer_inventario()
            if not debe:
                raise RuntimeError(
                    "El primer inventario ya se ha ejecutado previamente para "
                    f"el equipo {self.machine_id!r}: {motivo}"
                )
            if volumenes is not None:
                volumenes_a_escanear = [
                    volumen
                    for volumen in volumenes
                    if volumen.disponible
                    and not self.contrato.should_exclude_mount(
                        volumen.ruta_raiz or volumen.letra
                    )
                ]
            else:
                alcance = self.reportar_alcance()
                volumenes_a_escanear = list(alcance.volumenes_a_escanear)
            total_volumenes = len(volumenes_a_escanear)
            logger.info(
                "Inicio primer inventario machine_id=%s total_volumenes=%d",
                self.machine_id,
                total_volumenes,
            )
            ejecucion = EjecucionPrimerInventario(
                machine_id=self.machine_id,
                total_volumenes=total_volumenes,
                callback_progreso=callback_progreso,
            )
            hilo = threading.Thread(
                target=self._bucle_escaneo,
                args=(ejecucion, list(volumenes_a_escanear)),
                daemon=True,
                name="jarvis-primer-inventario",
            )
            ejecucion.hilo = hilo
            self._ejecucion_actual = ejecucion
            hilo.start()
        return ejecucion

    def _volumenes_reales(self, sistema: InfoSistema) -> list[VolumeInfo]:
        """Enumera los volúmenes reales del sistema operativo."""
        so = sistema.sistema_operativo
        if so == "Windows":
            return enumerar_volumenes_windows()
        if so == "Linux":
            return enumerar_volumenes_linux()
        if so == "Darwin":
            return enumerar_volumenes_macos()
        return []

    def _bucle_escaneo(
        self,
        ejecucion: EjecucionPrimerInventario,
        volumenes_a_escanear: list[VolumeInfo],
    ) -> None:
        """Cuerpo de la ejecución en segundo plano (hilo daemon).

        Crea su propia instancia de `SystemInventoryStorage` sobre la misma
        base de datos para que la conexión SQLite se abra en este hilo (SQLite
        no permite compartir una conexión creada en otro hilo). El modo WAL
        permite que varias conexiones lean/escriban la misma base de forma
        segura sin modificar `system_inventory_storage` (unidad cerrada).
        La importación es perezosa para evitar la dependencia circular con
        `system_inventory_storage` (que importa de `system_inventory`).
        """
        from src.hands.system_inventory_storage import SystemInventoryStorage

        almacenamiento = SystemInventoryStorage(self.storage.db_path)
        resultado_final: dict = {
            "volumenes_planificados": len(volumenes_a_escanear),
            "volumenes_completados": 0,
            "entradas_procesadas": 0,
            "errores": 0,
            "scan_ids": [],
            "interrumpido": False,
        }
        try:
            total = len(volumenes_a_escanear)
            completados = 0
            scan_ids: list[str] = []
            entradas_procesadas = 0
            errores = 0

            for volumen in volumenes_a_escanear:
                if ejecucion.solicitado_cancelar:
                    break
                raiz = volumen.ruta_raiz or volumen.letra
                # Esperar mientras esté pausado y no se cancele.
                while ejecucion.solicitado_pausa and not ejecucion.solicitado_cancelar:
                    time.sleep(0.25)

                scan_id = f"primero-{uuid.uuid4()}"
                started_at = datetime.now().isoformat()
                scan_ids.append(scan_id)

                almacenamiento.begin_scan_run(
                    scan_id=scan_id,
                    machine_id=self.machine_id,
                    volume=raiz,
                    mode="completo",
                    started_at=started_at,
                )

                ejecucion._notificar_progreso(
                    volumen_actual=raiz,
                    volumenes_completados=completados,
                    scan_ids=list(scan_ids),
                    cobertura_global=(
                        round(completados / total * 100.0, 2) if total > 0 else 0.0
                    ),
                )

                contador_volumen = 0
                lote: list[dict] = []
                errores_volumen = 0

                def progreso_volumen(progreso_vol: ProgresoRecorrido) -> None:
                    nonlocal errores_volumen
                    errores_volumen = progreso_vol.errores
                    avance_actual = (
                        progreso_vol.cobertura / 100.0 if total > 0 else 0.0
                    )
                    cobertura_global = (
                        (completados + avance_actual) / total * 100.0
                        if total > 0
                        else 0.0
                    )
                    ejecucion._notificar_progreso(
                        volumen_actual=raiz,
                        volumenes_completados=completados,
                        entradas_procesadas=entradas_procesadas
                        + progreso_vol.entradas_procesadas,
                        archivos_procesados=progreso_vol.archivos_procesados,
                        errores=errores + progreso_vol.errores,
                        errores_por_categoria=dict(
                            progreso_vol.errores_por_categoria
                        ),
                        cobertura_global=round(cobertura_global, 2),
                        entrada_actual=progreso_vol.entrada_actual,
                        scan_ids=list(scan_ids),
                    )

                try:
                    for entrada in RecorridoVolumen(
                        volumen=raiz,
                        raiz=raiz,
                        contrato=self.contrato,
                        maquina_id=self.machine_id,
                        callback_progreso=progreso_volumen,
                        callback_control=ejecucion.control,
                        limite_recursos=None,
                        medidor_recursos=self.medidor,
                    ).recorrer():
                        if ejecucion.solicitado_cancelar:
                            break
                        lote.append(
                            {
                                "entry_id": f"e-{uuid.uuid4()}",
                                "absolute_path": entrada.absolute_path,
                                "relative_path": entrada.relative_path,
                                "name": entrada.name,
                                "extension": entrada.extension,
                                "entry_type": entrada.entry_type.value,
                                "size_bytes": entrada.size_bytes,
                                "modified_at": entrada.modified_at,
                                "created_at": entrada.created_at,
                                "accessed_at": entrada.accessed_at,
                                "attributes": entrada.attributes,
                                "excluded": entrada.excluded,
                                "source": entrada.source,
                                "last_checked_at": entrada.last_checked_at,
                            }
                        )
                        contador_volumen += 1
                        if len(lote) >= self.tamano_lote_entradas:
                            almacenamiento.insert_file_entries(
                                scan_id, self.machine_id, raiz, lote
                            )
                            entradas_procesadas += len(lote)
                            lote = []
                finally:
                    if lote:
                        almacenamiento.insert_file_entries(
                            scan_id, self.machine_id, raiz, lote
                        )
                        entradas_procesadas += len(lote)

                resultado_volumen = (
                    "interrumpido" if ejecucion.solicitado_cancelar else "ok"
                )
                almacenamiento.end_scan_run(
                    scan_id=scan_id,
                    finished_at=datetime.now().isoformat(),
                    result=resultado_volumen,
                    entries_count=contador_volumen,
                    errors_count=errores_volumen,
                )
                errores += errores_volumen
                completados += 1
                logger.info(
                    "Volumen completado machine_id=%s volumen=%s entradas=%d errores=%d resultado=%s",
                    self.machine_id,
                    safe_log_path(raiz),
                    contador_volumen,
                    errores_volumen,
                    resultado_volumen,
                )
                ejecucion._notificar_progreso(
                    volumenes_completados=completados,
                    entradas_procesadas=entradas_procesadas,
                    errores=errores,
                    scan_ids=list(scan_ids),
                    cobertura_global=(
                        round(completados / total * 100.0, 2) if total > 0 else 0.0
                    ),
                )
                if ejecucion.solicitado_cancelar:
                    break

            if ejecucion.solicitado_cancelar:
                estado_final = EstadoPrimerInventario.INTERRUMPIDO
                resultado_final["interrumpido"] = True
            else:
                estado_final = EstadoPrimerInventario.COMPLETADO

            resultado_final.update(
                {
                    "volumenes_completados": completados,
                    "entradas_procesadas": entradas_procesadas,
                    "errores": errores,
                    "scan_ids": scan_ids,
                }
            )
            logger.info(
                "Fin primer inventario machine_id=%s volumenes_completados=%d entradas_procesadas=%d errores_totales=%d scan_ids=%d",
                self.machine_id,
                completados,
                entradas_procesadas,
                errores,
                len(scan_ids),
            )
            ejecucion._finalizar(estado_final, resultado_final)
        except Exception as exc:  # no se deja el hilo colgado ni se propaga al llamante
            resultado_final["error"] = str(exc)
            ejecucion._finalizar(EstadoPrimerInventario.INTERRUMPIDO, resultado_final)

    def ejecucion_actual(self) -> Optional[EjecucionPrimerInventario]:
        """Devuelve la ejecución en curso, si la hay."""
        with self._lock:
            return self._ejecucion_actual


# ---------------------------------------------------------------------------
# Política configurable de refresco y actualizaciones incrementales bajo
# demanda del inventario (3.8.5.1.4.8.2).
#
# Capa de decisión sobre cuándo y qué refrescar de forma incremental, sin
# volver a escanear los volúmenes completos en cada petición. Reutiliza los
# mecanismos de refresco del almacenamiento
# (`SystemInventoryStorage.refrescar_entrada_por_ruta`,
# `refrescar_volumen`, `refrescar_incremental_global`) y clasifica las entradas
# por caducidad (`ConfigCaducidad` / `esta_caducado`, unidad 3.8.5.1.4.5.9).
# ---------------------------------------------------------------------------

class ModoRefresco(Enum):
    """Modos de la política de refresco del inventario.

    `BAJO_DEMANDA`: solo se refresca cuando se solicita explícitamente.
    `POR_CADUCIDAD`: se refresca cuando las entradas del volumen están caducadas
        u obsoletas según el TTL configurado.
    `PROGRAMADA`: se refresca cuando ha transcurrido el intervalo configurado
        desde el último refresco de ese volumen.
    `DESACTIVADO`: no se refresca automáticamente (solo bajo demanda explícita).
    """

    BAJO_DEMANDA = "bajo_demanda"
    POR_CADUCIDAD = "por_caducidad"
    PROGRAMADA = "programada"
    DESACTIVADO = "desactivado"


@dataclass
class ConfigRefresco:
    """Configuración de la política de refresco del inventario.

    Todos los valores son opcionales y `None` significa "sin restricción". Los
    umbrales de tiempo se configuran a partir de mediciones reales del equipo
    o necesidades del consumidor, nunca por inferencia.
    """

    modo: ModoRefresco = ModoRefresco.BAJO_DEMANDA
    """Modo de refresco activo."""

    ttl_segundos: Optional[float] = None
    """Tiempo máximo de vida en segundos de una entrada antes de considerarla
    caducada (solo modo `POR_CADUCIDAD`). `None` = sin caducidad por tiempo."""

    intervalo_segundos: Optional[float] = None
    """Intervalo mínimo en segundos entre refrescos automáticos de un mismo
    volumen (solo modo `PROGRAMADA`). `None` = sin intervalo."""

    volumenes_incluir: Optional[list[str]] = None
    """Volúmenes que se consideran para refresco automático. `None` =
    todos los detectados. Lista vacía = ninguno."""

    volumenes_excluir: list[str] = field(default_factory=list)
    """Volúmenes excluidos del refresco automático."""

    rutas_incluir: Optional[list[str]] = None
    """Rutas candidatas a refresco bajo demanda explícito. `None` = cualquier
    ruta registrada en el último escaneo del volumen."""

    rutas_excluir: list[str] = field(default_factory=list)
    """Rutas excluidas del refresco bajo demanda."""

    max_entradas_por_refresco: Optional[int] = None
    """Límite de seguridad de entradas a refrescar en una operación.
    `None` = sin límite."""

    refrescar_solo_caducadas: bool = True
    """Si `True`, el refresco automático solo toca volúmenes con entradas
    caducadas u obsoletas."""


@dataclass
class ResultadoRefresco:
    """Resultado de una operación de refresco incremental."""

    modo: str
    """Modo de refresco aplicado."""

    volume: Optional[str]
    """Volumen refrescado (`None` si fue una ruta individual)."""

    ruta: Optional[str]
    """Ruta refrescada (`None` si fue un volumen)."""

    entradas_refrescadas: int
    """Número de entradas cuya `last_checked_at` se actualizó."""

    cambios_detectados: int
    """Número de entradas cuyo tamaño cambió respecto a lo almacenado."""

    existen: int
    """Entradas que siguen existiendo en el sistema de archivos."""

    no_existen: int
    """Entradas que ya no existen en el sistema de archivos."""

    last_checked_at: Optional[str]
    """Marca de tiempo de la última comprobación."""

    escaneo_completo_evitado: bool
    """`True` si la operación usó refresco incremental y no un recorrido
    completo de volumen (`RecorridoVolumen`). Siempre `True` en esta política."""

    razon: Optional[str]
    """Explicación legible del resultado (por qué se refrescó o no)."""

    detalle: dict
    """Resultado crudo devuelto por el almacenamiento."""


class PoliticaRefresco:
    """
    Política configurable de refresco del inventario de archivos.

    Decide cuándo y qué refrescar de forma incremental, sin volver a escanear
    los volúmenes completos en cada petición. Reutiliza los mecanismos de
    refresco del almacenamiento y clasifica las entradas por caducidad.

    `storage` es una instancia de `SystemInventoryStorage` inyectada para
    evitar la dependencia circular entre `system_inventory` y
    `system_inventory_storage`.

    Responsabilidades:
    1. Decidir si un volumen necesita refresco según el modo y la caducidad de
       sus entradas (`necesita_refresco_volumen`).
    2. Refrescar un volumen solo si lo necesita
       (`refrescar_volumen_si_necesario`), sin recorrido completo de volumen.
    3. Refrescar bajo demanda una ruta individual (`refrescar_ruta_bajo_demanda`).
    4. Refrescar selectivamente solo los volúmenes que lo necesitan
       (`refrescar_incremental_selectivo`), nunca todos los volúmenes
       completos en cada petición.
    5. Registrar el historial de refrescos para decisiones programadas.
    """

    def __init__(
        self,
        storage: Any,
        machine_id: str,
        config: Optional[ConfigRefresco] = None,
        medidor: Optional[MedidorRecursosSistema] = None,
    ) -> None:
        self.storage = storage
        self.machine_id = machine_id
        self._config = config or ConfigRefresco()
        self.medidor = medidor or MedidorRecursosSistema()
        self._lock = threading.Lock()
        self._historial: list[ResultadoRefresco] = []
        self._ultimo_refresco_por_volumen: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Configuración
    # ------------------------------------------------------------------ #
    def configurar(self, config: ConfigRefresco) -> None:
        """Reemplaza la configuración de la política de refresco."""
        with self._lock:
            self._config = config

    def config_actual(self) -> ConfigRefresco:
        """Devuelve una copia de la configuración vigente."""
        with self._lock:
            cfg = self._config
            return ConfigRefresco(
                modo=cfg.modo,
                ttl_segundos=cfg.ttl_segundos,
                intervalo_segundos=cfg.intervalo_segundos,
                volumenes_incluir=(
                    list(cfg.volumenes_incluir)
                    if cfg.volumenes_incluir is not None
                    else None
                ),
                volumenes_excluir=list(cfg.volumenes_excluir),
                rutas_incluir=(
                    list(cfg.rutas_incluir)
                    if cfg.rutas_incluir is not None
                    else None
                ),
                rutas_excluir=list(cfg.rutas_excluir),
                max_entradas_por_refresco=cfg.max_entradas_por_refresco,
                refrescar_solo_caducadas=cfg.refrescar_solo_caducadas,
            )

    # ------------------------------------------------------------------ #
    # Filtros de elegibilidad
    # ------------------------------------------------------------------ #
    def _volumen_es_elegible(self, volume: str) -> bool:
        """Devuelve `True` si el volumen está incluido y no excluido."""
        cfg = self._config
        if cfg.volumenes_incluir is not None and volume not in cfg.volumenes_incluir:
            return False
        if volume in cfg.volumenes_excluir:
            return False
        return True

    def _ruta_es_elegible(self, ruta_absoluta: str) -> bool:
        """Devuelve `True` si la ruta está incluida y no excluida."""
        cfg = self._config
        if cfg.rutas_incluir is not None and ruta_absoluta not in cfg.rutas_incluir:
            return False
        if ruta_absoluta in cfg.rutas_excluir:
            return False
        return True

    # ------------------------------------------------------------------ #
    # Decisión de refresco por volumen (caducidad de las entradas)
    # ------------------------------------------------------------------ #
    def necesita_refresco_volumen(
        self, volume: str
    ) -> tuple[bool, str, dict]:
        """
        Decide si un volumen necesita un refresco incremental.

        Retorna `(necesita, motivo, info)` donde `info` contiene:
        `entradas_totales`, `entradas_caducadas`, `scan_id`,
        `edad_maxima_segundos` y `modo`.

        Lógica:
        - Modo `DESACTIVADO`: nunca necesita refresco automático.
        - Sin escaneo previo: no hay nada que refrescar incrementalmente.
        - Modo `POR_CADUCIDAD`: necesita refresco si alguna entrada del último
          escaneo está caducada u obsoleta según el TTL.
        - Modo `PROGRAMADA`: necesita refresco si ha transcurrido el intervalo
          configurado desde el último refresco de ese volumen.
        - Modo `BAJO_DEMANDA`: nunca necesita refresco automático (solo bajo
          demanda explícita).
        """
        cfg = self._config
        info: dict = {
            "volume": volume,
            "entradas_totales": 0,
            "entradas_caducadas": 0,
            "scan_id": None,
            "edad_maxima_segundos": None,
            "modo": cfg.modo.value,
        }

        if cfg.modo == ModoRefresco.DESACTIVADO:
            info["razon"] = "Modo de refresco desactivado."
            return False, "Refresco automático desactivado por política.", info

        if not self._volumen_es_elegible(volume):
            info["razon"] = "Volumen no elegible por política (excluido o no incluido)."
            return False, "Volumen no elegible para refresco automático.", info

        scan = self.storage.get_latest_scan(self.machine_id, volume)
        if scan is None:
            info["razon"] = "No hay escaneo previo para este equipo y volumen."
            return (
                False,
                "No hay escaneo previo del volumen para refrescar.",
                info,
            )

        info["scan_id"] = scan.get("scan_id")

        # Modo PROGRAMADA: decidir por intervalo transcurrido desde el último refresco.
        if cfg.modo == ModoRefresco.PROGRAMADA:
            intervalo = cfg.intervalo_segundos
            if intervalo is None:
                info["razon"] = "Modo programado sin intervalo configurado."
                return False, "Modo programado sin intervalo de refresco.", info
            ultimo = self._ultimo_refresco_por_volumen.get(volume)
            scan_started = scan.get("started_at") or ""
            referencia = ultimo or scan_started
            edad: Optional[float] = None
            if referencia:
                try:
                    t0 = datetime.fromisoformat(referencia)
                    t1 = datetime.now()
                    if t0.tzinfo is not None:
                        t1 = t1.astimezone()
                    edad = max(0.0, (t1 - t0).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    edad = None
            if edad is not None and edad < intervalo:
                info["razon"] = (
                    f"Intervalo de refresco no transcurrido "
                    f"({edad:.1f}s < {intervalo:.1f}s)."
                )
                return (
                    False,
                    f"Intervalo de refresco no transcurrido para {volume}.",
                    info,
                )
            info["razon"] = (
                "Intervalo de refresco transcurrido o sin previo refresco."
            )
            return True, f"Volumen {volume} listo para refresco programado.", info

        # Modo POR_CADUCIDAD (y BAJO_DEMANDA, solo para informar caducidad):
        # evaluar caducidad de las entradas del último escaneo.
        try:
            entradas = self.storage.obtener_entradas_escaneo(scan["scan_id"])
        except AttributeError:
            # Almacenamiento sin acceso público a entradas: no se puede
            # evaluar caducidad por entrada.
            info["razon"] = (
                "El almacenamiento no expone las entradas del escaneo; no se "
                "puede evaluar caducidad por entrada."
            )
            return False, "No se pueden leer las entradas del escaneo.", info

        info["entradas_totales"] = len(entradas)

        umbral = ConfigCaducidad(ttl_segundos=cfg.ttl_segundos)
        caducadas = 0
        edad_maxima: Optional[float] = None
        for e in entradas:
            entrada = InventoryEntry(
                machine_id=e.get("machine_id", self.machine_id),
                volume=e.get("volume", volume),
                absolute_path=e.get("absolute_path", ""),
                relative_path=e.get("relative_path", ""),
                name=e.get("name", ""),
                extension=e.get("extension", ""),
                entry_type=EntryType(
                    e.get("entry_type", EntryType.OTHER.value)
                ),
                size_bytes=int(e.get("size_bytes", 0) or 0),
                modified_at=e.get("modified_at", "") or "",
                created_at=e.get("created_at", "") or "",
                accessed_at=e.get("accessed_at"),
                attributes=list(e.get("attributes", []) or []),
                excluded=bool(e.get("excluded", False)),
                exclusion_reason=e.get("exclusion_reason"),
                source=e.get("source", "filesystem_scan"),
                last_checked_at=e.get("last_checked_at", "") or "",
            )
            resultado = esta_caducado(entrada, umbral)
            if resultado.estado in (
                EstadoCaducidad.OBSOLETO,
                EstadoCaducidad.EXPIRADO,
            ):
                caducadas += 1
            edad = resultado.edad_segundos
            if edad is not None and (edad_maxima is None or edad > edad_maxima):
                edad_maxima = edad

        info["entradas_caducadas"] = caducadas
        info["edad_maxima_segundos"] = edad_maxima

        if cfg.modo == ModoRefresco.BAJO_DEMANDA:
            info["razon"] = (
                f"{caducadas}/{info['entradas_totales']} entradas caducadas; "
                "refresco solo bajo demanda explícita."
            )
            return False, "Modo bajo demanda: no hay refresco automático.", info

        # POR_CADUCIDAD: refrescar si hay entradas caducadas.
        if caducadas > 0:
            info["razon"] = (
                f"{caducadas} entradas caducadas u obsoletas de "
                f"{info['entradas_totales']}; se requiere refresco incremental."
            )
            return True, f"Volumen {volume} tiene entradas caducadas.", info

        info["razon"] = (
            f"Todas las {info['entradas_totales']} entradas están vigentes; "
            "no se requiere refresco."
        )
        return False, "No hay entradas caducadas; refresco innecesario.", info

    # ------------------------------------------------------------------ #
    # Operaciones de refresco incremental
    # ------------------------------------------------------------------ #
    def _registrar(self, resultado: ResultadoRefresco) -> None:
        with self._lock:
            self._historial.append(resultado)
            if resultado.volume and resultado.last_checked_at:
                self._ultimo_refresco_por_volumen[resultado.volume] = (
                    resultado.last_checked_at
                )

    def _resultado_desde_storage(
        self,
        modo: str,
        storage_result: dict,
        volume: Optional[str] = None,
        ruta: Optional[str] = None,
        razon: Optional[str] = None,
        evitar_escaneo_completo: bool = True,
    ) -> ResultadoRefresco:
        return ResultadoRefresco(
            modo=modo,
            volume=volume,
            ruta=ruta,
            entradas_refrescadas=int(
                storage_result.get("entradas_refrescadas", 0)
            ),
            cambios_detectados=int(storage_result.get("cambios_detectados", 0)),
            existen=int(storage_result.get("existentes", 0)),
            no_existen=int(storage_result.get("no_existentes", 0)),
            last_checked_at=storage_result.get("last_checked_at"),
            escaneo_completo_evitado=evitar_escaneo_completo,
            razon=razon or storage_result.get("razon"),
            detalle=storage_result,
        )

    def refrescar_volumen_si_necesario(self, volume: str) -> ResultadoRefresco:
        """
        Refresca un volumen solo si la política lo indica.

        Usa `refrescar_volumen` del almacenamiento (revalidación puntual de
        las entradas existentes: existencia y tamaño), nunca un recorrido
        completo de volumen (`RecorridoVolumen`). Si el volumen no necesita
        refresco, retorna un resultado con `entradas_refrescadas == 0` y la
        razón, sin tocar el almacenamiento.
        """
        necesita, motivo, _info = self.necesita_refresco_volumen(volume)
        if not necesita:
            logger.info(
                "Refresco no necesario volumen=%s modo=%s motivo=%s",
                safe_log_path(volume),
                self._config.modo.value,
                motivo,
            )
            return self._resultado_desde_storage(
                modo=self._config.modo.value,
                storage_result={
                    "entradas_refrescadas": 0,
                    "cambios_detectados": 0,
                    "existentes": 0,
                    "no_existentes": 0,
                    "last_checked_at": None,
                    "razon": motivo,
                },
                volume=volume,
                razon=motivo,
                evitar_escaneo_completo=True,
            )

        storage_result = self.storage.refrescar_volumen(self.machine_id, volume)
        resultado = self._resultado_desde_storage(
            modo=self._config.modo.value,
            storage_result=storage_result,
            volume=volume,
            razon=motivo,
            evitar_escaneo_completo=True,
        )
        logger.info(
            "Refresco volumen=%s modo=%s entradas_refrescadas=%d cambios=%d existen=%d no_existen=%d escaneo_completo_evitado=%s",
            safe_log_path(volume),
            resultado.modo,
            resultado.entradas_refrescadas,
            resultado.cambios_detectados,
            resultado.existen,
            resultado.no_existen,
            resultado.escaneo_completo_evitado,
        )
        self._registrar(resultado)
        return resultado

    def refrescar_ruta_bajo_demanda(
        self, ruta_absoluta: str, volume: str
    ) -> ResultadoRefresco:
        """
        Refresco incremental bajo demanda de una única ruta.

        Se ejecuta siempre que se solicite explícitamente, independientemente
        del modo automático, siempre que la ruta sea elegible según la política
        de inclusión/exclusión de rutas. Usa `refrescar_entrada_por_ruta` del
        almacenamiento (revalidación puntual, sin recorrido completo de volumen).
        """
        if not self._ruta_es_elegible(ruta_absoluta):
            logger.info(
                "Ruta excluida por política de refresco volumen=%s ruta=%s",
                safe_log_path(volume),
                safe_log_path(ruta_absoluta),
            )
            return self._resultado_desde_storage(
                modo=ModoRefresco.BAJO_DEMANDA.value,
                storage_result={
                    "entradas_refrescadas": 0,
                    "cambios_detectados": 0,
                    "existentes": 0,
                    "no_existentes": 0,
                    "last_checked_at": None,
                    "razon": "Ruta excluida por política de refresco.",
                },
                volume=volume,
                ruta=ruta_absoluta,
                razon="Ruta excluida por política de rutas (no incluida o excluida).",
                evitar_escaneo_completo=True,
            )

        storage_result = self.storage.refrescar_entrada_por_ruta(
            self.machine_id, volume, ruta_absoluta
        )
        resultado = self._resultado_desde_storage(
            modo=ModoRefresco.BAJO_DEMANDA.value,
            storage_result=storage_result,
            volume=volume,
            ruta=ruta_absoluta,
            razon="Refresco bajo demanda de ruta individual.",
            evitar_escaneo_completo=True,
        )
        logger.info(
            "Refresco ruta bajo demanda volumen=%s ruta=%s entradas_refrescadas=%d cambios=%d",
            safe_log_path(volume),
            safe_log_path(ruta_absoluta),
            resultado.entradas_refrescadas,
            resultado.cambios_detectados,
        )
        self._registrar(resultado)
        return resultado

    def refrescar_incremental_selectivo(
        self, volumenes_disponibles: list[str]
    ) -> dict:
        """
        Refresca solo los volúmenes que lo necesitan según la política.

        Nunca refresca todos los volúmenes completos en cada petición: evalúa
        cada volumen disponible y solo aplica
        `refrescar_volumen_si_necesario` a los que la política marca como
        necesarios.

        Retorna un resumen agregado con `por_volumen` y totales.
        """
        cfg = self._config
        if cfg.modo == ModoRefresco.DESACTIVADO:
            return {
                "machine_id": self.machine_id,
                "modo": cfg.modo.value,
                "total_volumenes_evaluados": len(volumenes_disponibles),
                "volumenes_refrescados": 0,
                "volumenes_no_necesitaban_refresco": len(
                    volumenes_disponibles
                ),
                "entradas_refrescadas_total": 0,
                "cambios_detectados_total": 0,
                "por_volumen": [],
                "razon": "Refresco automático desactivado por política.",
            }

        por_volumen: list[dict] = []
        entradas_total = 0
        cambios_total = 0
        refrescados = 0
        no_necesitaban = 0

        for volume in volumenes_disponibles:
            if not self._volumen_es_elegible(volume):
                continue
            resultado = self.refrescar_volumen_si_necesario(volume)
            entrada = {
                "volume": resultado.volume,
                "modo": resultado.modo,
                "entradas_refrescadas": resultado.entradas_refrescadas,
                "cambios_detectados": resultado.cambios_detectados,
                "existen": resultado.existen,
                "no_existen": resultado.no_existen,
                "last_checked_at": resultado.last_checked_at,
                "razon": resultado.razon,
                "escaneo_completo_evitado": resultado.escaneo_completo_evitado,
            }
            por_volumen.append(entrada)
            entradas_total += resultado.entradas_refrescadas
            cambios_total += resultado.cambios_detectados
            if resultado.entradas_refrescadas > 0:
                refrescados += 1
            else:
                no_necesitaban += 1

        logger.info(
            "Refresco selectivo modo=%s volumenes_evaluados=%d volumenes_refrescados=%d volumenes_sin_refresco=%d entradas_refrescadas_total=%d cambios_detectados_total=%d",
            cfg.modo.value,
            len(volumenes_disponibles),
            refrescados,
            no_necesitaban,
            entradas_total,
            cambios_total,
        )

        return {
            "machine_id": self.machine_id,
            "modo": cfg.modo.value,
            "total_volumenes_evaluados": len(volumenes_disponibles),
            "volumenes_refrescados": refrescados,
            "volumenes_no_necesitaban_refresco": no_necesitaban,
            "entradas_refrescadas_total": entradas_total,
            "cambios_detectados_total": cambios_total,
            "por_volumen": por_volumen,
            "razon": None,
        }

    def decidir_volumenes_a_refrescar(
        self, volumenes_disponibles: list[str]
    ) -> list[str]:
        """
        Devuelve los volúmenes que necesitan refresco según la política,
        sin ejecutar el refresco. Útil para planificar antes de actuar.
        """
        a_refrescar: list[str] = []
        for volume in volumenes_disponibles:
            if not self._volumen_es_elegible(volume):
                continue
            necesita, _, _ = self.necesita_refresco_volumen(volume)
            if necesita:
                a_refrescar.append(volume)
        return a_refrescar

    # ------------------------------------------------------------------ #
    # Historial y observabilidad
    # ------------------------------------------------------------------ #
    def historial(self) -> list[ResultadoRefresco]:
        """Devuelve una copia del historial de operaciones de refresco."""
        with self._lock:
            return list(self._historial)

    def ultimo_refresco_por_volumen(self) -> dict[str, str]:
        """Devuelve la marca de tiempo del último refresco por volumen."""
        with self._lock:
            return dict(self._ultimo_refresco_por_volumen)


# ---------------------------------------------------------------------------
# Coincidencia de exclusiones de usuario (3.8.5.1.4.8.3).
# ---------------------------------------------------------------------------

def _coincide_alguna_exclusion_ruta(
    ruta_absoluta: str, exclusiones: list[str]
) -> bool:
    """
    Devuelve True si `ruta_absoluta` coincide con alguna exclusión de usuario.

    Coincide si es igual a la exclusión o se encuentra dentro de la carpeta
    excluida (prefijo seguido de separador de ruta). La comparación respeta
    mayúsculas/minúsculas según el sistema de archivos (`os.path.normcase`),
    de modo que en Windows "C:\\Datos" y "c:\\datos" son la misma ubicación.
    """
    if not exclusiones:
        return False
    ruta = os.path.normcase(os.path.abspath(ruta_absoluta))
    for exclusion in exclusiones:
        if not exclusion:
            continue
        normalizada = os.path.normcase(os.path.abspath(exclusion))
        if ruta == normalizada:
            return True
        carpeta = normalizada.rstrip("\\/") + os.sep
        if ruta.startswith(carpeta):
            return True
    return False


# ---------------------------------------------------------------------------
# Resultado de una ejecución de escaneo controlado (3.8.5.1.4.8.3).
# ---------------------------------------------------------------------------

@dataclass
class ResultadoEscaneo:
    """
    Resultado observable de una ejecución de escaneo controlado.

    Todos los campos provienen de la ejecución real sobre el sistema de
    archivos y el almacenamiento SQLite: identificador de scan, volumen,
    ruta escaneada, modo, contadores de entradas, directorios y archivos,
    errores agrupados por categoría, exclusiones, cobertura y estado de
    finalización. Nunca se fabrican ni simulan los valores.
    """

    scan_id: str
    """Identificador de la ejecución de escaneo en `scan_runs`."""
    volumen: str
    """Volumen escaneado."""
    ruta: str
    """Ruta raíz escaneada (raíz de volumen o subárbol de ruta)."""
    modo: str
    """Modo de escaneo: `"completo"` o `"incremental"`."""
    entradas_procesadas: int = 0
    archivos_procesados: int = 0
    directorios_procesados: int = 0
    errores: int = 0
    errores_por_categoria: dict[str, int] = field(default_factory=dict)
    exclusiones: int = 0
    cobertura: float = 0.0
    iniciado_en: str = ""
    finalizado_en: str = ""
    resultado: str = "interrumpido"  # "ok", "interrumpido", "error", "parcial"
    interrumpido: bool = False
    completado: bool = False


def _almacenamiento_predeterminado() -> Any:
    """
    Devuelve una instancia de almacenamiento sobre la ruta por defecto.

    La importación es perezosa para evitar la dependencia circular:
    `system_inventory_storage` importa de `system_inventory`.
    """
    from src.hands.system_inventory_storage import SystemInventoryStorage

    return SystemInventoryStorage()


class EscanerRutaVolumen:
    """
    Motor de escaneo controlado por volumen o por ruta (3.8.5.1.4.8.3).

    Ejecuta un recorrido real de `RecorridoVolumen` sobre la raíz indicada
    (raíz de un volumen o cualquier subárbol de ruta), registra la ejecución
    en `scan_runs` con `begin_scan_run`/`end_scan_run`, inserta las entradas
    en lotes atómicos con `insert_file_entries` y respeta:

    - exclusiones del contrato de inventario (técnicas y de usuario),
    - callbacks de progreso y control (pausa/cancelar),
    - límites de recursos (`LimiteRecursos` con `MedidorRecursosSistema`),
    - aislamiento por equipo (`machine_id`).

    Es no destructivo: cada ejecución genera un `scan_id` nuevo, las entradas
    de escaneos previos se conservan como historial y el nuevo scan_run queda
    como el más reciente del volumen o ruta. No borra ni sobrescribe entradas
    previas ni modifica el contenido de ningún archivo (privacidad, lectura
    solo de metadatos).

    `storage` es una instancia de `SystemInventoryStorage` inyectada para
    evitar la dependencia circular con `system_inventory_storage`.
    """

    def __init__(
        self,
        volumen: str,
        raiz: str,
        contrato: InventoryContract,
        maquina_id: str,
        storage: Any,
        modo: str = "completo",
        callback_progreso: Optional[Callable[[ProgresoRecorrido], None]] = None,
        callback_control: Optional[Callable[[], ControlRecorrido]] = None,
        limite_recursos: Optional[LimiteRecursos] = None,
        medidor_recursos: Optional[MedidorRecursosSistema] = None,
        tamano_lote_entradas: int = 500,
    ) -> None:
        if modo not in ("completo", "incremental"):
            raise ValueError(
                f"Modo de escaneo no válido: {modo!r}. "
                "Use 'completo' o 'incremental'."
            )
        self.volumen = volumen
        self.raiz = os.path.abspath(raiz)
        self.contrato = contrato
        self.maquina_id = maquina_id
        self.storage = storage
        self.modo = modo
        self.callback_progreso = callback_progreso
        self.callback_control = callback_control
        self.limite_recursos = limite_recursos
        self.medidor_recursos = medidor_recursos or MedidorRecursosSistema()
        self.tamano_lote_entradas = max(1, int(tamano_lote_entradas))

    def ejecutar(self) -> ResultadoEscaneo:
        """
        Ejecuta el escaneo real y retorna su resultado observable.

        Crea el scan_run, recorre la raíz con `RecorridoVolumen`, inserta
        las entradas en lotes y finaliza el scan_run con `"ok"` o
        `"interrumpido"` (si se solicitó pausa/cancelar). Libera el bloqueo
        de concurrencia incluso ante fallos.
        """
        from src.hands.system_inventory_storage import (
            SCAN_RESULT_INTERRUPTED,
            SCAN_RESULT_OK,
        )

        scan_id = f"scan-{uuid.uuid4()}"
        iniciado_en = datetime.now().isoformat()
        logger.info(
            "Inicio de escaneo scan_id=%s volumen=%s modo=%s raiz=%s",
            scan_id,
            self.volumen,
            self.modo,
            safe_log_path(self.raiz),
        )
        self.storage.connect()
        self.storage.record_machine(self.maquina_id, created_at=iniciado_en)
        self.storage.begin_scan_run(
            scan_id=scan_id,
            machine_id=self.maquina_id,
            volume=self.volumen,
            mode=self.modo,
            started_at=iniciado_en,
        )

        recorrido = RecorridoVolumen(
            volumen=self.volumen,
            raiz=self.raiz,
            contrato=self.contrato,
            maquina_id=self.maquina_id,
            callback_progreso=self.callback_progreso,
            callback_control=self.callback_control,
            limite_recursos=self.limite_recursos,
            medidor_recursos=self.medidor_recursos,
        )

        entradas_procesadas = 0
        archivos_procesados = 0
        directorios_procesados = 0
        lote: list[dict] = []
        interrumpido = False

        try:
            for entrada in recorrido.recorrer():
                entradas_procesadas += 1
                if entrada.entry_type == EntryType.FILE:
                    archivos_procesados += 1
                elif entrada.entry_type == EntryType.DIRECTORY:
                    directorios_procesados += 1

                lote.append(
                    {
                        "entry_id": f"e-{uuid.uuid4()}",
                        "absolute_path": entrada.absolute_path,
                        "relative_path": entrada.relative_path,
                        "name": entrada.name,
                        "extension": entrada.extension,
                        "entry_type": entrada.entry_type.value,
                        "size_bytes": entrada.size_bytes,
                        "modified_at": entrada.modified_at,
                        "created_at": entrada.created_at,
                        "accessed_at": entrada.accessed_at,
                        "attributes": entrada.attributes,
                        "excluded": entrada.excluded,
                        "exclusion_reason": entrada.exclusion_reason,
                        "source": entrada.source,
                        "last_checked_at": entrada.last_checked_at,
                    }
                )
                if len(lote) >= self.tamano_lote_entradas:
                    self.storage.insert_file_entries(
                        scan_id, self.maquina_id, self.volumen, lote
                    )
                    lote = []

            if recorrido.ejecucion_parcial:
                interrumpido = True
        finally:
            if lote:
                self.storage.insert_file_entries(
                    scan_id, self.maquina_id, self.volumen, lote
                )

        finalizado_en = datetime.now().isoformat()
        resultado = SCAN_RESULT_INTERRUPTED if interrumpido else SCAN_RESULT_OK
        progreso = recorrido.progreso
        self.storage.end_scan_run(
            scan_id=scan_id,
            finished_at=finalizado_en,
            result=resultado,
            entries_count=entradas_procesadas,
            errors_count=progreso.errores,
            exclusions_count=progreso.exclusiones,
            coverage_estimate=str(round(progreso.cobertura, 2)),
        )

        logger.info(
            "Fin de escaneo scan_id=%s volumen=%s modo=%s resultado=%s entradas=%d archivos=%d directorios=%d errores=%d exclusiones=%d cobertura=%.2f%%",
            scan_id,
            self.volumen,
            self.modo,
            resultado,
            entradas_procesadas,
            archivos_procesados,
            directorios_procesados,
            progreso.errores,
            progreso.exclusiones,
            round(progreso.cobertura, 2),
        )

        return ResultadoEscaneo(
            scan_id=scan_id,
            volumen=self.volumen,
            ruta=self.raiz,
            modo=self.modo,
            entradas_procesadas=entradas_procesadas,
            archivos_procesados=archivos_procesados,
            directorios_procesados=directorios_procesados,
            errores=progreso.errores,
            errores_por_categoria=progreso.errores_por_categoria,
            exclusiones=progreso.exclusiones,
            cobertura=round(progreso.cobertura, 2),
            iniciado_en=iniciado_en,
            finalizado_en=finalizado_en,
            resultado=resultado,
            interrumpido=interrumpido,
            completado=not interrumpido,
        )


def escanear_ruta(
    ruta_absoluta: str,
    contrato: Optional[InventoryContract] = None,
    maquina_id: Optional[str] = None,
    storage: Any = None,
    modo: str = "completo",
    **kwargs: Any,
) -> ResultadoEscaneo:
    """
    Escanea un subárbol de ruta concreto (no necesariamente la raíz de un
    volumen) (3.8.5.1.4.8.3).

    El volumen se deriva de la ruta con `_volumen_de_ruta`. Registra el
    escaneo en el almacenamiento y retorna un `ResultadoEscaneo` observable.

    Parametros:
    - `ruta_absoluta`: ruta a escanear (se convierte a absoluta).
    - `contrato`: `InventoryContract` con alcance, exclusiones técnicas y de
      usuario, y privacidad. Por defecto, `default_contract()`.
    - `maquina_id`: identificador del equipo. Por defecto, `generate_machine_id()`.
    - `storage`: `SystemInventoryStorage` inyectada. Por defecto, instancia
      sobre la ruta por defecto del inventario.
    - `modo`: `"completo"` o `"incremental"`.
    - `kwargs`: argumentos reenviados a `EscanerRutaVolumen`
      (callbacks, `limite_recursos`, `medidor_recursos`, `tamano_lote_entradas`).
    """
    if storage is None:
        storage = _almacenamiento_predeterminado()
    if maquina_id is None:
        maquina_id = generate_machine_id()
    if contrato is None:
        contrato = default_contract()
    volumen = _volumen_de_ruta(ruta_absoluta)
    return EscanerRutaVolumen(
        volumen=volumen,
        raiz=ruta_absoluta,
        contrato=contrato,
        maquina_id=maquina_id,
        storage=storage,
        modo=modo,
        **kwargs,
    ).ejecutar()


def escanear_volumen(
    volumen: str,
    ruta_raiz: str,
    contrato: Optional[InventoryContract] = None,
    maquina_id: Optional[str] = None,
    storage: Any = None,
    modo: str = "completo",
    **kwargs: Any,
) -> ResultadoEscaneo:
    """
    Escanea la raíz de un volumen (o ruta indicada como raíz de volumen)
    (3.8.5.1.4.8.3).

    Equivalente a `escanear_ruta` con el volumen e identificador de volumen
    explícitos. Registra el escaneo en el almacenamiento y retorna un
    `ResultadoEscaneo` observable.
    """
    if storage is None:
        storage = _almacenamiento_predeterminado()
    if maquina_id is None:
        maquina_id = generate_machine_id()
    if contrato is None:
        contrato = default_contract()
    return EscanerRutaVolumen(
        volumen=volumen,
        raiz=ruta_raiz,
        contrato=contrato,
        maquina_id=maquina_id,
        storage=storage,
        modo=modo,
        **kwargs,
    ).ejecutar()


def reconstruir_catalogo(
    volumen: str,
    raiz: str,
    contrato: Optional[InventoryContract] = None,
    maquina_id: Optional[str] = None,
    storage: Any = None,
    **kwargs: Any,
) -> ResultadoEscaneo:
    """
    Reconstrucción controlada del catálogo de un volumen o ruta (3.8.5.1.4.8.3).

    Ejecuta un escaneo completo (`modo="completo"`) sobre el volumen o ruta
    indicados, respetando exclusiones técnicas y de usuario, límites de
    recursos, pausa y cancelación. Cada reconstrucción genera un `scan_id`
    nuevo: las entradas de escaneos previos se conservan como historial y el
    nuevo scan_run pasa a ser el más reciente del volumen o ruta, sin borrar
    ni sobrescribir entradas previas (no destructivo).
    """
    kwargs.pop("modo", None)
    return escanear_volumen(
        volumen=volumen,
        ruta_raiz=raiz,
        contrato=contrato,
        maquina_id=maquina_id,
        storage=storage,
        modo="completo",
        **kwargs,
    )
