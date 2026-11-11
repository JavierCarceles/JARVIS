"""
Clasificador de candidatos de aplicacion por tipo de lanzamiento propio de cada SO.

Unidad 3.8.5.1.4.7.1: clasifica candidatos del inventario (ejecutables, bundles,
paquetes, accesos directos, URI y lanzadores) sin asumir que todo archivo
ejecutable es una aplicacion GUI lanzable.

Este modulo NO lanza aplicaciones, no escribe en entities.json ni modifica el
catalogo conocido. Solo clasifica, deduplica por destino real y reporta
evidencia y nivel de confianza de cada clasificacion, para que consumidores
(posteriores: preflight, resolucion, planner) decidan que abrir.

Dependencias reales reutilizadas:
- src.hands.application_preflight.ApplicationPreflight.validate_launch_destination
  (validacion de destino: ejecutable .exe, acceso directo .lnk, URI admitida).
- src.hands.system_inventory.InventoryEntry (entrada de inventario, opcional como entrada).
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.hands.application_preflight import ApplicationPreflight
from src.hands.system_inventory import EntryType, InventoryEntry


# ---------------------------------------------------------------------------
# Tipos de lanzamiento (vocabulario compartido con ApplicationPreflight)
# ---------------------------------------------------------------------------

class LaunchType(str, Enum):
    """Tipo de lanzamiento propio de cada SO, segun el destino real observado."""

    EJECUTABLE = ApplicationPreflight.LAUNCH_TYPE_EXECUTABLE      # "ejecutable"
    ACCESO_DIRECTO = ApplicationPreflight.LAUNCH_TYPE_SHORTCUT    # "acceso_directo"
    URI_APLICACION = ApplicationPreflight.LAUNCH_TYPE_URI         # "uri_aplicacion"
    PAQUETE = ApplicationPreflight.LAUNCH_TYPE_PACKAGE            # "paquete"
    BUNDLE = ApplicationPreflight.LAUNCH_TYPE_BUNDLE              # "bundle"
    LANZADOR = ApplicationPreflight.LAUNCH_TYPE_LAUNCHER          # "lanzador"

    @classmethod
    def valores_admitidos(cls) -> frozenset[str]:
        return frozenset(item.value for item in cls)

    @classmethod
    def es_valido(cls, valor: Optional[str]) -> bool:
        return valor is not None and valor in cls.valores_admitidos()


# ---------------------------------------------------------------------------
# Subtipos de entrada (clasificacion de rol, sin asumir GUI por extension)
# ---------------------------------------------------------------------------

class LaunchSubtype(str, Enum):
    """Rol observado o inferido del candidato. Nunca se asume GUI solo por extension .exe."""

    GUI_APLICACION = "gui_aplicacion"
    HERRAMIENTA_CLI = "herramienta_cli"
    SERVICIO = "servicio"
    CONTROLADOR = "controlador"
    BIBLIOTECA = "biblioteca"
    INSTALADOR = "instalador"
    ACTUALIZADOR = "actualizador"
    DESINSTALADOR = "desinstalador"
    COMPONENTE_AUXILIAR = "componente_auxiliar"
    DESCONOCIDO = "desconocido"


# Niveles de confianza de una clasificacion.
CONFIANZA_NINGUNA = "ninguna"
CONFIANZA_BAJA = "baja"
CONFIANZA_MEDIA = "media"
CONFIANZA_ALTA = "alta"

# Subsistemas PE de Windows (campo Subsystem del Optional Header).
IMAGE_SUBSYSTEM_UNKNOWN = 0
IMAGE_SUBSYSTEM_GUI = 2      # Aplicacion de ventanas (GUI)
IMAGE_SUBSYSTEM_CUI = 3      # Aplicacion de consola (CLI / herramienta de linea de comandos)

CONFIDENCIAS_VALIDAS = frozenset({
    CONFIANZA_NINGUNA, CONFIANZA_BAJA, CONFIANZA_MEDIA, CONFIANZA_ALTA,
})


# Esquemas URI conocidos como lanzadores de aplicaciones de escritorio.
# No son esquemas admitidos para lanzamiento generico por validate_launch_destination;
# se clasifican como lanzador pero su lanzabilidad depende del preflight.
_ESQUEMAS_URI_LANZADOR = frozenset({
    "steam", "epic", "uplay", "origin", "battle.net", "battlenet",
    "com.epicgames.launcher", "uplayplay", "rockstar", "gog",
    "msteams", "zoommtg", "discord",
})

# Nombres de ejecutables reconocidos como herramientas de consola/CLI (evidencia real).
_NOMBRES_CLI = frozenset({
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "python", "python.exe", "pythonw", "pythonw.exe", "pip", "pip.exe",
    "ssh", "ssh.exe", "scp", "scp.exe", "git", "git.exe",
    "net", "net.exe", "ipconfig", "ipconfig.exe", "tasklist", "tasklist.exe",
    "taskkill", "taskkill.exe", "schtasks", "schtasks.exe", "systeminfo",
    "systeminfo.exe", "whoami", "whoami.exe", "ping", "ping.exe",
    "tracert", "tracert.exe", "nslookup", "nslookup.exe",
})

# Palabras clave de rol en nombre o ruta.
_PALABRAS_DESINSTALADOR = frozenset({"uninstall", "uninst", "desinstal", "unwise"})
_PALABRAS_INSTALADOR = frozenset({"setup", "install", "instalador", "msiexec", "instalador"})
_PALABRAS_ACTUALIZADOR = frozenset({"update", "updater", "actualizar", "actualizador", "update.exe"})
_PALABRAS_SERVICIO = frozenset({"service", "svc", "services", "servicio"})
_PALABRAS_AUXILIAR = frozenset({"helper", "helpers", "aux", "componente", "runonce", "stub"})

# Extensiones y sus roles directos.
_EXTENSION_BIBLIOTECA = frozenset({".dll", ".lib", ".so", ".dylib", ".a"})
_EXTENSION_CONTROLADOR = frozenset({".sys", ".drv", ".kext"})
_EXTENSION_BUNDLE_WINDOWS = frozenset({".appx", ".msix", ".appbundle", ".msixbundle"})
_EXTENSION_ACCESO_DIRECTO = frozenset({".lnk"})


# ---------------------------------------------------------------------------
# Utilidades de sistema real (lectura sin efectos secundarios)
# ---------------------------------------------------------------------------

def _es_ruta_windows(valor: Optional[str]) -> bool:
    if not valor or not isinstance(valor, str):
        return False
    v = valor.strip()
    if v.startswith("\\\\"):
        return True
    return len(v) >= 2 and v[0].isalpha() and v[1] == ":"


def _esquema_uri(valor: Optional[str]) -> Optional[str]:
    """Devuelve el esquema de URI si valor tiene uno y no es ruta de Windows."""
    if not valor or not isinstance(valor, str):
        return None
    v = valor.strip()
    if _es_ruta_windows(v):
        return None
    match = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", v)
    return match.group(1).lower() if match else None


def _nombre_sin_extension(ruta: Optional[str]) -> str:
    if not ruta:
        return ""
    return Path(ruta).stem


def _volumen_de_ruta(ruta_absoluta: str) -> str:
    p = Path(ruta_absoluta)
    if os.name == "nt":
        drive = p.drive
        return drive if drive else str(p.anchor)
    return p.anchor


def _ahora_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Lectura de subsistema PE de un ejecutable Windows (GUI vs CLI/consola)
# ---------------------------------------------------------------------------

def _leer_subsistema_pe(ruta: str) -> Optional[int]:
    """
    Lee el campo Subsystem del encabezado PE de un ejecutable Windows.

    Retorna:
      IMAGE_SUBSYSTEM_GUI (2) si es aplicacion de ventanas.
      IMAGE_SUBSYSTEM_CUI (3) si es aplicacion de consola / herramienta CLI.
      IMAGE_SUBSYSTEM_UNKNOWN (0) si no se puede leer o no es un PE valido.
      None en SO no Windows, archivo inexistente o cualquier error de lectura.
    """
    if os.name != "nt":
        return None
    if not ruta or not os.path.isfile(ruta):
        return None
    try:
        with open(ruta, "rb") as f:
            # DOS header: e_lfanew en el offset 0x3C (puntero al encabezado PE).
            f.seek(0x3C)
            e_lfanew_bytes = f.read(4)
            if len(e_lfanew_bytes) < 4:
                return None
            e_lfanew = int.from_bytes(e_lfanew_bytes, "little")

            # Firma PE en e_lfanew.
            f.seek(e_lfanew)
            pe_signature = f.read(4)
            if pe_signature != b"PE\x00\x00":
                return None

            # COFF header: SizeOfOptionalHeader en el offset 16 del COFF header.
            # El COFF header empieza en e_lfanew + 4.
            f.seek(e_lfanew + 20)
            size_opt_bytes = f.read(2)
            if len(size_opt_bytes) < 2:
                return None

            # Magic al inicio del Optional Header (e_lfanew + 24).
            f.seek(e_lfanew + 24)
            magic_bytes = f.read(2)
            if len(magic_bytes) < 2:
                return None
            magic = int.from_bytes(magic_bytes, "little")

            # Subsystem esta en el offset 0x44 (68) del Optional Header para
            # PE32 (0x10B) y PE32+ (0x20B).
            subsys_offset = e_lfanew + 24 + 0x44
            f.seek(subsys_offset)
            subsys_bytes = f.read(2)
            if len(subsys_bytes) < 2:
                return None
            return int.from_bytes(subsys_bytes, "little")
    except (OSError, ValueError):
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Lectura de version y producto de archivo (Windows, API real via ctypes)
# ---------------------------------------------------------------------------

def leer_version_archivo_windows(ruta: str) -> Optional[dict[str, str]]:
    """
    Lee metadatos de version de un archivo PE de Windows (ProductName,
    ProductVersion, FileVersion, CompanyName) mediante la API del SO
    (version.dll a traves de ctypes, sin dependencias externas).

    Retorna None en SO no Windows, archivo inexistente, sin recursos de
    version o cualquier error de lectura. Nunca lanza excepcion.
    """
    if os.name != "nt":
        return None
    if not ruta or not os.path.isfile(ruta):
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(ruta, None)
        if not size:
            return None
        data = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(ruta, 0, size, data):
            return None
        # "\\VarFileInfo\\Translation" devuelve un arreglo de pares
        # (langid, charsetid) de DWORD, no un string: se lee como c_uint.
        lang_id: Optional[int] = None
        charset_id: Optional[int] = None
        try:
            translation_ptr = ctypes.c_void_p()
            largo = ctypes.c_uint(0)
            if ctypes.windll.version.VerQueryValueW(
                data, "\\VarFileInfo\\Translation",
                ctypes.byref(translation_ptr), ctypes.byref(largo),
            ):
                if translation_ptr and largo.value >= 4:
                    pares = ctypes.cast(
                        translation_ptr, ctypes.POINTER(ctypes.c_uint16)
                    )
                    lang_id = int(pares[0])
                    charset_id = int(pares[1])
        except (ValueError, TypeError, OSError):
            lang_id = None
            charset_id = None
        if lang_id is None or charset_id is None:
            return None
        block = f"\\StringFileInfo\\{lang_id:04X}{charset_id:04X}\\"
        resultado: dict[str, str] = {}
        for clave in ("ProductName", "ProductVersion", "FileVersion", "CompanyName"):
            valor_ptr = ctypes.c_void_p()
            largo_val = ctypes.c_uint(0)
            if ctypes.windll.version.VerQueryValueW(
                data, block + clave, ctypes.byref(valor_ptr), ctypes.byref(largo_val),
            ):
                if valor_ptr and largo_val.value > 0:
                    valor = ctypes.cast(valor_ptr, ctypes.c_wchar_p).value
                    if valor:
                        resultado[clave] = valor
        return resultado or None
    except (OSError, AttributeError, ValueError, TypeError):
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resolucion de destino de acceso directo (.lnk) via API real del SO
# ---------------------------------------------------------------------------

def resolver_target_acceso_directo(ruta_lnk: str) -> Optional[str]:
    """
    Resuelve el destino de un acceso directo .lnk de Windows mediante
    Shell.Application de PowerShell (API real del equipo).

    Retorna None si no es Windows, no es .lnk, falla PowerShell o el destino
    no es un ejecutable existente. Nunca lanza excepcion.
    """
    if os.name != "nt":
        return None
    if not ruta_lnk or not ruta_lnk.casefold().endswith(".lnk"):
        return None
    if not os.path.isfile(ruta_lnk):
        return None
    carpeta = os.path.dirname(ruta_lnk).replace("'", "''")
    nombre = os.path.basename(ruta_lnk).replace("'", "''")
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "$shell = New-Object -ComObject Shell.Application; "
        "$lnk = $shell.NameSpace('__DIR__').ParseName('__ARCHIVO__').GetLink; "
        "if ($lnk -ne $null) { $lnk.TargetPath } else { '' }"
    ).replace("__DIR__", carpeta).replace("__ARCHIVO__", nombre)
    env = os.environ.copy()
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10, env=env,
        )
        if proc.returncode != 0:
            return None
        target = (proc.stdout or "").strip().strip('"')
        if not target:
            return None
        target = os.path.abspath(target)
        return target if (os.path.isfile(target) and target.casefold().endswith(".exe")) else None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resultado de clasificacion
# ---------------------------------------------------------------------------

@dataclass
class LaunchClassification:
    """
    Resultado completo de clasificar un candidato de aplicacion.

    Todos los campos son observables o inferidos con evidencia registrada;
    ninguno se asume solo por extension de archivo.
    """

    candidate_id: str
    name: str
    nombre_comercial: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    absolute_path: Optional[str] = None
    destination: Optional[str] = None
    volume: Optional[str] = None
    launch_type: Optional[str] = None
    launch_subtype: LaunchSubtype = LaunchSubtype.DESCONOCIDO
    es_lanzable: bool = False
    evidencia: list[str] = field(default_factory=list)
    confianza: str = CONFIANZA_NINGUNA
    version: Optional[str] = None
    producto: Optional[str] = None
    fuente: str = "inventario"
    ultima_comprobacion: str = ""
    razon: str = ""
    requiere_preflight: bool = True
    advertencias: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.confianza not in CONFIDENCIAS_VALIDAS:
            self.confianza = CONFIANZA_BAJA
        if self.ultima_comprobacion == "":
            self.ultima_comprobacion = _ahora_iso()

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "nombre_comercial": self.nombre_comercial,
            "aliases": list(self.aliases),
            "absolute_path": self.absolute_path,
            "destination": self.destination,
            "volume": self.volume,
            "launch_type": self.launch_type,
            "launch_subtype": self.launch_subtype.value,
            "es_lanzable": self.es_lanzable,
            "evidencia": list(self.evidencia),
            "confianza": self.confianza,
            "version": self.version,
            "producto": self.producto,
            "fuente": self.fuente,
            "ultima_comprobacion": self.ultima_comprobacion,
            "razon": self.razon,
            "requiere_preflight": self.requiere_preflight,
            "advertencias": list(self.advertencias),
        }


# ---------------------------------------------------------------------------
# Clasificador
# ---------------------------------------------------------------------------

class LaunchClassifier:
    """
    Clasifica candidatos de inventario por tipo de lanzamiento y rol real.

    No lanza aplicaciones, no modifica entidades conocidas ni persiste nada:
    devuelve objetos LaunchClassification listos para consumir por preflight,
    resolucion de aplicaciones o el planificador.
    """

    def __init__(self, preflight: Optional[ApplicationPreflight] = None) -> None:
        self.preflight = preflight or ApplicationPreflight()

    # ------------------------------------------------------------------ #
    # Entrada
    # ------------------------------------------------------------------ #
    @staticmethod
    def _candidate_a_campos(candidate: Any) -> dict[str, Any]:
        """Normaliza una entrada de candidato (dict o InventoryEntry) a campos comunes."""
        if isinstance(candidate, InventoryEntry):
            d = candidate.to_dict()
            return {
                "candidate_id": d.get("absolute_path", ""),
                "name": d.get("name", ""),
                "destination": d.get("absolute_path"),
                "source": d.get("source", "filesystem_scan"),
                "volume": d.get("volume"),
                "launch_type": d.get("launch_type"),
                "last_checked_at": d.get("last_checked_at", ""),
            }
        if not isinstance(candidate, dict):
            return {
                "candidate_id": "",
                "name": "",
                "destination": None,
                "source": "desconocida",
                "volume": None,
                "launch_type": None,
                "last_checked_at": "",
            }
        return {
            "candidate_id": str(candidate.get("candidate_id", candidate.get("absolute_path", ""))),
            "name": str(candidate.get("name", "")),
            "destination": candidate.get("absolute_path") or candidate.get("destination"),
            "source": candidate.get("source", "inventario"),
            "volume": candidate.get("volume"),
            "launch_type": candidate.get("launch_type"),
            "last_checked_at": str(candidate.get("last_checked_at", "")),
        }

    # ------------------------------------------------------------------ #
    # Clasificacion de un solo candidato
    # ------------------------------------------------------------------ #
    def classify_candidate(self, candidate: Any) -> LaunchClassification:
        """Clasifica un candidato individual y devuelve su LaunchClassification."""
        campos = self._candidate_a_campos(candidate)
        candidate_id = campos["candidate_id"] or _nombre_sin_extension(campos["destination"]) or "desconocido"
        name = campos["name"] or _nombre_sin_extension(campos["destination"]) or "desconocido"
        destination = campos["destination"]
        source = campos["source"]
        volume = campos["volume"]
        preclassified = campos["launch_type"]
        last_checked = campos["last_checked_at"]

        clasificacion = LaunchClassification(
            candidate_id=candidate_id,
            name=name,
            absolute_path=destination,
            destination=destination,
            volume=volume,
            fuente=source,
            ultima_comprobacion=last_checked or _ahora_iso(),
            razon="Sin destino de lanzamiento identificable.",
        )

        if not destination or not isinstance(destination, str) or not destination.strip():
            clasificacion.launch_type = None
            clasificacion.launch_subtype = LaunchSubtype.DESCONOCIDO
            clasificacion.es_lanzable = False
            clasificacion.confianza = CONFIANZA_NINGUNA
            clasificacion.evidencia = ["destino_vacio"]
            clasificacion.razon = "El candidato no tiene destino de lanzamiento."
            return clasificacion

        destino = destination.strip()
        clasificacion.absolute_path = destino
        clasificacion.destination = destino

        # Nombre comercial y aliases (independientes del nombre del ejecutable, requisito .7.5).
        version_info = leer_version_archivo_windows(destino) if os.path.isfile(destino) else None
        nombre_comercial: Optional[str] = None
        producto: Optional[str] = None
        version: Optional[str] = None
        if version_info:
            nombre_comercial = version_info.get("ProductName")
            producto = version_info.get("ProductName") or version_info.get("CompanyName")
            version = version_info.get("ProductVersion") or version_info.get("FileVersion")
            clasificacion.evidencia.append("version_recurso_leida")
        clasificacion.nombre_comercial = nombre_comercial
        clasificacion.producto = producto
        clasificacion.version = version

        aliases = self._construir_aliases(name, destino, nombre_comercial, version_info)
        clasificacion.aliases = aliases

        # --- Tipo de lanzamiento ---------------------------------------
        launch_type: Optional[str] = preclassified if LaunchType.es_valido(preclassified) else None
        if not launch_type:
            launch_type = self._detectar_launch_type(destino, name)

        clasificacion.launch_type = launch_type

        # --- Subtipo de rol --------------------------------------------
        clasificacion.launch_subtype = self._detectar_subtipo(destino, name, launch_type, version_info)

        # --- Lanzabilidad y confianza (evidencia real, no solo extension) --
        es_lanzable, confianza, evidencia_extra, advertencias = self._evaluar_lanzabilidad(
            destino, name, launch_type, clasificacion.launch_subtype, version_info
        )
        clasificacion.es_lanzable = es_lanzable
        clasificacion.confianza = confianza
        clasificacion.evidencia.extend(evidencia_extra)
        clasificacion.advertencias.extend(advertencias)

        # Razon legible.
        clasificacion.razon = self._construir_razon(clasificacion)
        clasificacion.requiere_preflight = launch_type in (
            LaunchType.EJECUTABLE.value,
            LaunchType.ACCESO_DIRECTO.value,
            LaunchType.URI_APLICACION.value,
        )
        return clasificacion

    # ------------------------------------------------------------------ #
    # Deteccion de tipo de lanzamiento
    # ------------------------------------------------------------------ #
    def _detectar_launch_type(self, destino: str, name: str) -> Optional[str]:
        """Detecta el tipo de lanzamiento a partir del destino real (nunca solo por extension)."""

        # 1) URI de aplicación.
        esquema = _esquema_uri(destino)
        if esquema:
            if esquema in _ESQUEMAS_URI_LANZADOR:
                return LaunchType.LANZADOR.value
            validacion = self.preflight.validate_launch_destination(destino)
            if validacion.get("valid") and validacion.get("launch_type") == ApplicationPreflight.LAUNCH_TYPE_URI:
                return ApplicationPreflight.LAUNCH_TYPE_URI
            return None  # URI desconocida o esquema no admitido: no es lanzable confirmado

        # 2) Acceso directo .lnk (solo si existe realmente).
        if Path(destino).suffix.casefold() in _EXTENSION_ACCESO_DIRECTO:
            if os.path.isfile(destino):
                return LaunchType.ACCESO_DIRECTO.value
            return None

        # 3) Paquete/bundle de SO.
        nombre_lower = Path(destino).name.casefold()
        if nombre_lower.endswith(".app") and Path(destino).is_dir() and os.name != "nt":
            return LaunchType.BUNDLE.value  # bundle de macOS
        if Path(destino).suffix.casefold() in _EXTENSION_BUNDLE_WINDOWS:
            if os.path.isfile(destino):
                return LaunchType.PAQUETE.value
            return None

        # 4) Ejecutable .exe (candidato; lanzabilidad se decide por evidencia en _evaluar_lanzabilidad).
        if Path(destino).suffix.casefold() == ".exe":
            if os.path.isfile(destino):
                return LaunchType.EJECUTABLE.value
            return None

        return None

    # ------------------------------------------------------------------ #
    # Deteccion de subtipo de rol
    # ------------------------------------------------------------------ #
    def _detectar_subtipo(
        self, destino: str, name: str, launch_type: Optional[str], version_info: Optional[dict[str, str]]
    ) -> LaunchSubtype:
        nombre_lower = name.casefold()
        ruta_lower = destino.casefold() if destino else ""
        extension = Path(destino).suffix.casefold() if destino else ""

        if extension in _EXTENSION_BIBLIOTECA:
            return LaunchSubtype.BIBLIOTECA
        if extension in _EXTENSION_CONTROLADOR:
            return LaunchSubtype.CONTROLADOR

        if any(p in nombre_lower or p in ruta_lower for p in _PALABRAS_DESINSTALADOR):
            return LaunchSubtype.DESINSTALADOR
        if any(p in nombre_lower or p in ruta_lower for p in _PALABRAS_INSTALADOR):
            return LaunchSubtype.INSTALADOR
        if any(p in nombre_lower or p in ruta_lower for p in _PALABRAS_ACTUALIZADOR):
            return LaunchSubtype.ACTUALIZADOR
        if any(p in nombre_lower or p in ruta_lower for p in _PALABRAS_SERVICIO):
            return LaunchSubtype.SERVICIO
        if any(p in nombre_lower or p in ruta_lower for p in _PALABRAS_AUXILIAR):
            return LaunchSubtype.COMPONENTE_AUXILIAR

        if _nombre_sin_extension(destino).casefold() in _NOMBRES_CLI:
            return LaunchSubtype.HERRAMIENTA_CLI

        if launch_type == LaunchType.URI_APLICACION.value or launch_type == LaunchType.LANZADOR.value:
            return LaunchSubtype.GUI_APLICACION
        if launch_type == LaunchType.PAQUETE.value or launch_type == LaunchType.BUNDLE.value:
            return LaunchSubtype.GUI_APLICACION
        if launch_type == LaunchType.ACCESO_DIRECTO.value:
            # Un acceso directo suele abrir una aplicacion GUI; si el target
            # no se conoce, se trata como componente auxiliar pendiente.
            return LaunchSubtype.GUI_APLICACION

        if launch_type == LaunchType.EJECUTABLE.value:
            # Ejecutable real: con version de producto, se usa el subsistema PE
            # para diferenciar GUI (subsistema 2) de CLI/consola (subsistema 3).
            # Sin version_info ni PE legible se mantiene como desconocido.
            if version_info:
                subsistema = _leer_subsistema_pe(destino)
                if subsistema == IMAGE_SUBSYSTEM_CUI:
                    return LaunchSubtype.HERRAMIENTA_CLI
                return LaunchSubtype.GUI_APLICACION
            return LaunchSubtype.DESCONOCIDO

        return LaunchSubtype.DESCONOCIDO

    # ------------------------------------------------------------------ #
    # Lanzabilidad y confianza (evidencia real)
    # ------------------------------------------------------------------ #
    def _evaluar_lanzabilidad(
        self,
        destino: str,
        name: str,
        launch_type: Optional[str],
        subtype: LaunchSubtype,
        version_info: Optional[dict[str, str]],
    ) -> tuple[bool, str, list[str], list[str]]:
        """
        Decide si el candidato es realmente lanzable y con que confianza.

        Requisito .7.4: un archivo no se clasifica como lanzable solo por su
        extension; se necesita evidencia adicional del sistema (version,
        acceso directo resuelto, paquete, URI admitida, ubicacion real).
        """
        evidencia: list[str] = []
        advertencias: list[str] = []

        if launch_type is None:
            return False, CONFIANZA_NINGUNA, ["sin_tipo_de_lanzamiento"], advertencias

        # URI de aplicacion: lanzable solo si el esquema es admitido por
        # preflight; no requiere archivo en disco.
        if launch_type == LaunchType.URI_APLICACION.value:
            validacion = self.preflight.validate_launch_destination(destino)
            if validacion.get("valid"):
                evidencia.append("uri_admitida_validada")
                return True, CONFIANZA_ALTA, evidencia, advertencias
            advertencias.append("uri_esquema_no_admitido")
            return False, CONFIANZA_BAJA, ["uri_no_admitida"], advertencias

        # Lanzador URI (steam://, etc.): clasificacion de tipo sin archivo en
        # disco; su lanzabilidad depende de que el SO/adaptador lo admita.
        if launch_type == LaunchType.LANZADOR.value:
            advertencias.append("lanzador_uri_pendiente_de_preflight")
            return False, CONFIANZA_MEDIA, ["lanzador_uri"], advertencias

        if not os.path.exists(destino):
            advertencias.append("destino_no_existe_en_sistema")
            return False, CONFIANZA_BAJA, ["destino_inexistente"], advertencias

        # Acceso directo: lanzable si el target resuelve a un ejecutable real.
        if launch_type == LaunchType.ACCESO_DIRECTO.value:
            target = resolver_target_acceso_directo(destino)
            if target:
                evidencia.append("acceso_directo_target_resuelto")
                if version_info:
                    evidencia.append("version_recurso_leida")
                    return True, CONFIANZA_ALTA, evidencia, advertencias
                return True, CONFIANZA_MEDIA, evidencia, advertencias
            advertencias.append("acceso_directo_sin_target_valido")
            return False, CONFIANZA_BAJA, ["acceso_directo_rotu_o_invalido"], advertencias

        # Paquete / bundle: lanzable si el archivo existe realmente.
        if launch_type in (LaunchType.PAQUETE.value, LaunchType.BUNDLE.value):
            evidencia.append("paquete_presente_en_disco")
            if version_info:
                evidencia.append("version_recurso_leida")
                return True, CONFIANZA_MEDIA, evidencia, advertencias
            return True, CONFIANZA_BAJA, evidencia, advertencias

        # Ejecutable .exe: exige mas que la extension.
        if launch_type == LaunchType.EJECUTABLE.value and os.path.isfile(destino):
            evidencia.append("archivo_ejecutable_existente")
            if version_info:
                evidencia.append("version_recurso_leida")
                if self._parece_ubicacion_instalada(destino):
                    evidencia.append("ubicacion_de_instalacion_real")
                # Confianza alta solo con version + ubicacion real; media con solo version.
                if version_info and self._parece_ubicacion_instalada(destino):
                    return True, CONFIANZA_ALTA, evidencia, advertencias
                return True, CONFIANZA_MEDIA, evidencia, advertencias
            # .7.4: sin recursos de version, validar el encabezado PE como
            # evidencia adicional del sistema de que el archivo es un
            # ejecutable real, no solo un cambio de extension.
            subsistema_pe = _leer_subsistema_pe(destino)
            if subsistema_pe is not None:
                evidencia.append("encabezado_pel_valido")
                return True, CONFIANZA_BAJA, evidencia, advertencias
            # Solo extension .exe sin mas evidencia: NO se asume lanzable (.7.1, .7.4).
            advertencias.append("solo_extension_ejecutable_sin_evidencia")
            return False, CONFIANZA_BAJA, ["solo_extension_ejecutable"], advertencias

        return False, CONFIANZA_BAJA, ["tipo_sin_evidencia_suficiente"], advertencias

    @staticmethod
    def _parece_ubicacion_instalada(ruta: str) -> bool:
        """Heuristica suave de ubicacion de instalacion real (Program Files, etc.)."""
        if not ruta:
            return False
        r = ruta.casefold()
        marcadores = (
            "program files", "program files (x86)", "windows", "system32",
            "syswow64", "aplicaciones", "applications",
        )
        return any(m in r for m in marcadores)

    # ------------------------------------------------------------------ #
    # Aliases y nombre comercial
    # ------------------------------------------------------------------ #
    @staticmethod
    def _construir_aliases(
        name: str, destino: Optional[str], nombre_comercial: Optional[str],
        version_info: Optional[dict[str, str]],
    ) -> list[str]:
        """Construye aliases sin asumir que coincidan con el nombre del ejecutable (.7.5)."""
        aliases: list[str] = []
        vistos: set[str] = set()

        def anadir(valor: Optional[str]) -> None:
            if not valor:
                return
            v = str(valor).strip()
            if not v:
                return
            clave = v.casefold()
            if clave in vistos:
                return
            vistos.add(clave)
            aliases.append(v)

        anadir(name)
        anadir(nombre_comercial)
        anadir(_nombre_sin_extension(destino))
        if version_info:
            anadir(version_info.get("CompanyName"))
        return aliases

    # ------------------------------------------------------------------ #
    # Razon legible
    # ------------------------------------------------------------------ #
    @staticmethod
    def _construir_razon(clasificacion: LaunchClassification) -> str:
        partes = [
            f"tipo={clasificacion.launch_type or 'ninguno'}",
            f"subtipo={clasificacion.launch_subtype.value}",
            f"lanzable={'si' if clasificacion.es_lanzable else 'no'}",
            f"confianza={clasificacion.confianza}",
        ]
        if clasificacion.evidencia:
            partes.append("evidencia=" + ",".join(clasificacion.evidencia))
        if clasificacion.advertencias:
            partes.append("advertencias=" + ",".join(clasificacion.advertencias))
        return "; ".join(partes)

    # ------------------------------------------------------------------ #
    # Clasificacion en lote con deduplicacion por destino real (.7.7)
    # ------------------------------------------------------------------ #
    def classify_candidates(self, candidates: list[Any]) -> list[LaunchClassification]:
        """
        Clasifica una lista de candidatos y deduplica por identidad y destino
        real, no solo por nombre (.7.7).

        Requisitos:
        - Mismas rutas reales -> misma instalacion: se conserva la clasificacion
          con mayor confianza/evidencia, no se fusionan instalaciones distintas.
        - Rutas distintas -> instalaciones distintas: se conservan todas las
          rutas candidatas (.7.5).
        """
        clasificaciones = [self.classify_candidate(c) for c in candidates]

        # Agrupar por destino real normalizado (rutas existentes en disco).
        grupos: dict[str, list[LaunchClassification]] = {}
        sueltos: list[LaunchClassification] = []
        for c in clasificaciones:
            clave = _normalizar_destino_agrupamiento(c.destination, c.launch_type)
            if clave is None:
                sueltos.append(c)
            else:
                grupos.setdefault(clave, []).append(c)

        resultado: list[LaunchClassification] = []
        for clave, grupo in grupos.items():
            mejor = max(grupo, key=lambda c: (_puntos_confianza(c.confianza), len(c.evidencia)))
            resultado.append(mejor)
        resultado.extend(sueltos)

        resultado.sort(key=lambda c: (_puntos_confianza(c.confianza), len(c.evidencia)), reverse=True)
        return resultado

    # ------------------------------------------------------------------ #
    # Validacion previa al lanzamiento (.7.10)
    # ------------------------------------------------------------------ #
    def validar_destino_antes_de_lanzar(self, destino: str) -> dict[str, Any]:
        """
        Pasa un candidato a ser abierto por ApplicationPreflight y las
        politicas existentes (.7.10). No lanza nada; solo devuelve la decision
        estructurada del preflight.
        """
        return self.preflight.validate_launch_destination(destino)


def _normalizar_destino_agrupamiento(
    destino: Optional[str], launch_type: Optional[str]
) -> Optional[str]:
    """Clave de agrupamiento: ruta normalizada si existe en disco, else None."""
    if not destino or launch_type not in (
        LaunchType.EJECUTABLE.value,
        LaunchType.ACCESO_DIRECTO.value,
        LaunchType.PAQUETE.value,
        LaunchType.BUNDLE.value,
        LaunchType.URI_APLICACION.value,
    ):
        return None
    if launch_type == LaunchType.URI_APLICACION.value:
        return destino.strip().casefold()
    if not os.path.exists(destino):
        return None
    try:
        return os.path.normcase(os.path.abspath(destino))
    except (OSError, ValueError):
        return None


def _puntos_confianza(confianza: str) -> int:
    return {
        CONFIANZA_ALTA: 3,
        CONFIANZA_MEDIA: 2,
        CONFIANZA_BAJA: 1,
        CONFIANZA_NINGUNA: 0,
    }.get(confianza, 0)
