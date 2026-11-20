"""
Gestor universal de calibracion de aplicaciones para JARVIS.

El gestor coordina descubrimiento, preflight, apertura segura, preparacion de
ventanas, captura de monitor, calibracion visual universal y persistencia.

No contiene calibradores visuales especificos por aplicacion ni coordenadas,
resoluciones, offsets o DPI hardcodeados.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import shlex
import subprocess
import time
import unicodedata
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import sys as _sys

from src.desktop.native_imports import lazy_module as _lazy_module, lazy_windll as _lazy_windll

if _sys.platform == "win32":
    import pygetwindow as gw
else:
    gw = _lazy_module("pygetwindow")  # import nativo perezoso fuera de Windows

from src.core.config import get_calibration_config, get_macros_coords_path
from src.core.log import get_logger
from src.desktop.screen_manager import get_monitor_info, get_screen_manager
from src.hands.apps.application_preflight import get_application_preflight

logger = get_logger(__name__)


# ============================================================================
# WIN32
# ============================================================================

if _sys.platform == "win32":
    USER32 = ctypes.windll.user32
    KERNEL32 = ctypes.windll.kernel32
    ADVAPI32 = ctypes.windll.advapi32
else:
    # Fuera de Windows el acceso falla con NativeDependencyUnavailable explicito.
    USER32 = _lazy_windll("user32")
    KERNEL32 = _lazy_windll("kernel32")
    ADVAPI32 = _lazy_windll("advapi32")

GWL_STYLE = -16
GWL_EXSTYLE = -20
GW_OWNER = 4

WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_RESTORE = 9
SW_MAXIMIZE = 3

SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

HWND_TOP = 0

WM_CLOSE = 0x0010
WM_SYSCOMMAND = 0x0112
SC_CLOSE = 0xF060

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_INFORMATION_CLASS_ELEVATION = 20

WPF_SETMINPOSITION = 0x0001
WPF_RESTORETOMAXIMIZED = 0x0002


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


# ============================================================================
# TIPOS
# ============================================================================


class ApplicationType(Enum):
    CHROME = "chrome"
    EDGE = "edge"
    FIREFOX = "firefox"
    NOTEPAD = "notepad"
    CALCULATOR = "calculator"
    PAINT = "paint"
    EXPLORER = "explorer"
    CMD = "cmd"
    SPOTIFY = "spotify"
    GENERIC = "generic"


@dataclass
class CalibrationPreflightResult:
    allowed: bool
    application_name: str
    application_id: str = ""
    reason: Optional[str] = None
    checks: Dict[str, Any] = field(default_factory=dict)
    source: str = "internal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "application_name": self.application_name,
            "application_id": self.application_id,
            "reason": self.reason,
            "checks": dict(self.checks),
            "source": self.source,
        }


@dataclass
class CalibrationResult:
    application_name: str
    application_type: ApplicationType
    screen_number: int
    success: bool
    elements_count: int
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None
    calibration_data: Optional[Dict[str, Any]] = None
    skipped: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_name": self.application_name,
            "application_type": self.application_type.value,
            "screen_number": self.screen_number,
            "success": self.success,
            "elements_count": self.elements_count,
            "timestamp": self.timestamp,
            "error": self.error,
            "calibration_data": self.calibration_data,
            "skipped": self.skipped,
        }


@dataclass
class _WindowStateSnapshot:
    flags: int
    show_cmd: int
    min_x: int
    min_y: int
    max_x: int
    max_y: int
    normal_left: int
    normal_top: int
    normal_right: int
    normal_bottom: int


class LaunchState(Enum):
    """Estados de lanzamiento de aplicaciones, representados por separado.

    Modela el ciclo transitorio de verificacion de apertura:
    ABRIENDO -> PROCESO_INICIADO -> VENTANA_DETECTADA -> ABIERTA_VERIFICADA
    con ramas alternativas ABIERTA_SIN_VENTANA, FALLO y TIMEOUT.

    Estos estados son transitorios de la operacion de lanzamiento y no se
    mezclan con ApplicationState (estados persistentes de la aplicacion).
    """

    ABRIENDO = "abriendo"
    PROCESO_INICIADO = "proceso_iniciado"
    VENTANA_DETECTADA = "ventana_detectada"
    ABIERTA_VERIFICADA = "abierta_verificada"
    ABIERTA_SIN_VENTANA = "abierta_sin_ventana"
    FALLO = "fallo"
    TIMEOUT = "timeout"


# ============================================================================
# GESTOR
# ============================================================================


class CalibrationManager:
    """Coordinador universal de calibracion multiaplicacion y multimonitor."""

    ALLOWED_WINDOWS_GUI_NAMES = {
        "settings", "configuracion", "configuraci\u00f3n", "explorador_de_archivos",
        "file_explorer", "calculadora", "calculator", "bloc_de_notas", "notepad",
        "paint", "microsoft_paint", "fotos", "photos", "correo", "mail", "calendario",
        "calendar", "reproductor_multimedia", "media_player", "peliculas_y_tv",
        "movies_and_tv", "recortes", "snipping_tool", "sticky_notes", "notas_rapidas",
        "one_note", "onenote", "mapa_de_caracteres", "character_map", "reloj", "clock",
        "explorer", "cmd", "command_prompt",
    }

    IGNORED_EXACT_NAMES = {
        "help", "ayuda", "documentation", "documentacion", "documentaci\u00f3n", "more", "more...", ".lnk",
    }

    IGNORED_NAME_PARTS = (
        "uninstall", "desinstalar", "readme", "release notes", "notas de la versi\u00f3n",
        "notas de version", "changelog", "documentation", "documentaci\u00f3n", "documentacion",
        "manuals", "manual", "module docs", "module documentation", "frequently asked questions",
        "faq", "website", "on the web", "support center", "support centre", "support", "soporte",
        "redistributable", "sample desktop apps", "sample uwp apps", "sample", "samples",
        "tools for desktop apps", "tools for uwp apps", "developer command prompt",
        "developer powershell", "native tools command prompt", "cross tools command prompt",
        "powershell ise", "git bash", "git cmd", "node.js command prompt", "node.js documentation",
        "node.js website", "python manuals", "python module docs", "python documentation", "sdk",
        "software development kit", "install additional tools", "installer", "installation center",
        "centro de instalaci\u00f3n", "setup", "publisher",
    )

    ELEVATION_RISK_EXACT_NAMES = {
        "application_verifier", "application_verifier_wow", "application_verifier_x64",
        "administracion_de_equipos", "administracion_de_impresion", "administrador_de_hyper_v",
        "administrador_de_tareas", "directiva_de_seguridad_local", "editor_del_registro",
        "iniciador_iscsi", "monitor_de_recursos", "monitor_de_rendimiento", "programador_de_tareas",
        "servicios", "servicios_de_componentes", "visor_de_eventos", "windows_sandbox",
        "windows_defender_firewall_con_seguridad_avanzada", "diagnostico_de_memoria_de_windows",
        "desfragmentar_y_optimizar_unidades", "liberador_de_espacio_en_disco", "unidad_de_recuperacion",
        "seguridad_de_windows", "asistencia_rapida", "acceso_por_voz", "narrador", "lupa",
        "subtitulos_en_directo", "teclado_en_pantalla", "grabacion_de_acciones_de_usuario",
        "conexion_a_escritorio_remoto", "informacion_del_sistema", "configuracion_del_sistema",
    }

    ELEVATION_RISK_NAME_PARTS = (
        "application verifier", "application_verifier", "verifier", "administracion de equipos",
        "administracion de impresion", "administrador de hyper v", "administrador de tareas",
        "directiva de seguridad local", "editor del registro", "iniciador iscsi", "monitor de recursos",
        "monitor de rendimiento", "programador de tareas", "servicios de componentes", "active directory",
        "visor de eventos", "windows defender firewall", "diagnostico de memoria", "unidad de recuperacion",
        "security center", "security policy", "event viewer", "task scheduler", "computer management",
        "disk management", "device manager", "registry editor", "hyper v",
    )

    GAME_LAUNCHER_EXACT_NAMES = {
        "steam", "steam client", "epic games launcher", "riot client", "riot client services",
        "battle.net", "ubisoft connect", "ea app", "electronic arts", "rockstar games launcher",
        "gog galaxy", "xbox", "amazon games",
    }

    GAME_LAUNCHER_NAME_PARTS = (
        "epic games launcher", "riot client", "battle.net", "ubisoft connect",
        "rockstar games launcher", "gog galaxy",
    )

    GAME_LAUNCHER_EXECUTABLES = {
        "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "riotclientservices.exe",
        "riotclientux.exe", "battle.net.exe", "agent.exe", "upc.exe", "ubisoftconnect.exe",
        "upc_launcher.exe", "eadesktop.exe", "ealauncher.exe", "rockstargameslauncher.exe",
        "galaxyclient.exe", "xboxpcapp.exe", "gamingservices.exe",
    }

    GAME_EXACT_NAMES = {
        "league of legends", "valorant", "teamfight tactics", "legends of runeterra", "counter strike 2",
        "counter strike", "dota 2", "apex legends", "fortnite", "overwatch", "overwatch 2", "minecraft",
        "minecraft dungeons", "rocket league", "fall guys", "pubg", "destiny 2", "warframe", "gta v",
        "grand theft auto v", "grand theft auto", "red dead redemption 2", "elden ring", "dark souls",
        "dark souls ii", "dark souls iii", "cyberpunk 2077", "the witcher 3", "baldurs gate 3", "diablo iv",
        "diablo iii", "hearthstone", "world of warcraft", "starcraft ii", "heroes of the storm",
    }

    GAME_NAME_PARTS = (
        "league of legends", "valorant", "teamfight tactics", "legends of runeterra", "counter strike", "dota 2",
        "apex legends", "fortnite", "overwatch", "minecraft", "rocket league", "fall guys", "pubg", "destiny",
        "warframe", "grand theft auto", "red dead redemption", "elden ring", "dark souls", "cyberpunk 2077",
        "the witcher", "baldur's gate", "diablo", "hearthstone", "world of warcraft", "starcraft", "heroes of the storm",
    )

    GAME_APP_ID_PARTS = (
        "leagueoflegends", "valorant", "teamfighttactics", "legendsofruneterra", "counterstrike", "csgos", "dota2",
        "apexlegends", "fortnite", "minecraft", "rocketleague", "fallguys", "pubg", "destiny2", "warframe", "gta5",
        "gtav", "reddeadredemption", "eldenring", "darksouls", "cyberpunk2077", "thewitcher", "baldursgate3", "diablo",
        "hearthstone", "worldofwarcraft", "starcraft", "heroesofthestorm",
    )

    GAME_STEAM_APP_ID_PATTERN = re.compile(r"^steam[-_:]\d+$", re.IGNORECASE)
    GAME_INSTALL_PATH_PARTS = (
        "\\steam\\steamapps\\common\\", "\\steamapps\\common\\", "\\xboxgames\\",
        "\\gog games\\", "\\ubisoft game launcher\\games\\", "\\battle.net\\games\\",
    )
    GAME_INSTALL_ROOT_PARTS = ("\\epic games\\",)
    GAME_RIOT_INSTALL_PATH_PARTS = (
        "\\riot games\\league of legends\\", "\\riot games\\valorant\\",
        "\\riot games\\teamfight tactics\\", "\\riot games\\legends of runeterra\\",
    )
    GAME_LAUNCH_ARGUMENT_PARTS = (
        "steam://rungameid/", "steam://run/", "com.epicgames.launcher://apps/", "uplay://launch/",
        "goggalaxy://opengameview/", "battlenet://",
    )

    STORAGE_NAME_ALIASES = {
        "google_chrome": "chrome", "microsoft_edge": "edge", "mozilla_firefox": "firefox",
        "bloc_de_notas": "notepad", "calculadora": "calculator", "microsoft_paint": "paint",
        "explorador_de_archivos": "explorer", "explorador": "explorer", "command_prompt": "cmd",
        "symbol_of_the_system": "cmd",
    }

    VSCODE_EXACT_NAMES = {"visual studio code", "visual studio code insiders", "vs code", "code insiders"}
    VSCODE_NAME_PARTS = ("visual studio code", "vs code")
    VSCODE_EXECUTABLES = {"code.exe", "code-insiders.exe"}
    VSCODE_PATH_PARTS = ("\\microsoft vs code\\", "\\microsoft\\vs code\\", "\\visual studio code\\")

    NON_GUI_WINDOW_CLASSES = {"consolewindowclass", "cascadia_hosting_window_class", "tty"}
    MIN_GUI_WIDTH = 260
    MIN_GUI_HEIGHT = 180

    def __init__(self) -> None:
        self.screen_manager = get_screen_manager()
        from src.hands.calibration.universal_visual_calibrator import UniversalVisualCalibrator
        self.visual_calibrator = UniversalVisualCalibrator()
        self.calibration_config = get_calibration_config()

        self.calibrators: Dict[str, Any] = {}
        self._register_builtin_calibrators()
        self._calibration_pipeline: Any = None

        self._last_launch_before_hwnds: Set[int] = set()
        self._last_launch_before_pids: Set[int] = set()
        self._last_launch_owned_hwnds: Set[int] = set()
        self._last_launch_owned_pids: Set[int] = set()
        self._last_launch_window: Any = None
        self._last_launch_was_owned: bool = False
        self._last_launch_root_pid: Optional[int] = None
        self._last_launch_executable_path: Optional[str] = None
        self._last_launch_app_id: str = ""
        self._last_launch_state: Optional[LaunchState] = None
        self._last_launch_tipo_destino: Optional[str] = None
        self._last_launch_fuente: str = ""
        self._last_launch_destino_validado: Optional[str] = None
        self._last_launch_timestamps: Dict[str, Any] = {}
        self._last_launch_window_info: Dict[str, Any] = {}
        self._last_launch_evidence_path: Optional[str] = None
        self._temporary_browser_tab_open: bool = False
        self._temporary_browser_hwnd: Optional[int] = None

        self._application_metadata_by_name: Dict[str, List[Dict[str, str]]] = {}
        self._application_metadata_by_app_id: Dict[str, List[Dict[str, str]]] = {}
        self._application_metadata_all: List[Dict[str, str]] = []
        self._application_metadata_loaded = False
        self._preflight_checker: Optional[Callable[[Dict[str, str]], Any]] = (
            get_application_preflight().check
        )

        logger.info(r"[CALIBRATION-MANAGER] Gestor universal de calibracion inicializado")

    def _register_builtin_calibrators(self) -> None:
        """Prepara el registro de extensiones especificas sin usarlas como flujo principal.

        La calibracion normal, incluida Chrome, utiliza siempre el flujo
        universal de ventana -> monitor -> captura -> vision. Los calibradores
        especificos quedan disponibles unicamente para extensiones explicitas.
        """
        self.calibrators = {}
        logger.info(r"[CALIBRATION-MANAGER] Flujo universal habilitado para todas las aplicaciones; no se registra ningun calibrador especifico por defecto")

    # ========================================================================
    # REGISTRO / CAPACIDADES
    # ========================================================================

    def register_calibrator(self, application_name: str, calibrator: Any) -> None:
        key = self._get_storage_application_key(application_name)
        if not key:
            raise ValueError("Nombre de aplicacion vacio")
        if calibrator is None:
            raise ValueError("El calibrador no puede ser None")
        self.calibrators[key] = calibrator

    def get_available_applications(self) -> List[str]:
        discovered = self.discover_applications()
        return [str(item.get("name", "")).strip() for item in discovered if item.get("name")]

    def get_supported_applications(self) -> List[str]:
        return self.get_available_applications()

    def set_preflight_checker(self, checker: Optional[Callable[[Dict[str, str]], Any]]) -> None:
        self._preflight_checker = checker

    # ========================================================================
    # PREFLIGHT
    # ========================================================================

    @staticmethod
    def _normalize_preflight_result(result: Any, application: Dict[str, str], source: str) -> CalibrationPreflightResult:
        application_name = str(application.get("name", "")).strip()
        application_id = str(application.get("app_id", "")).strip()
        if isinstance(result, CalibrationPreflightResult):
            return result
        if isinstance(result, bool):
            return CalibrationPreflightResult(result, application_name, application_id,
                                              None if result else "Preflight rechaz\u00f3 la aplicaci\u00f3n", source=source)
        if isinstance(result, dict):
            allowed = result.get("allowed")
            if allowed is None:
                allowed = result.get("is_allowed", result.get("success", True))
            reason = result.get("reason") or result.get("error") or result.get("message")
            checks = result.get("checks", {})
            if not isinstance(checks, dict):
                checks = {}
            return CalibrationPreflightResult(bool(allowed), application_name, application_id,
                                              str(reason) if reason else None, checks, source)
        allowed = getattr(result, "allowed", None)
        if allowed is None:
            allowed = getattr(result, "is_allowed", getattr(result, "success", True))
        reason = getattr(result, "reason", None) or getattr(result, "error", None) or getattr(result, "message", None)
        checks = getattr(result, "checks", {})
        return CalibrationPreflightResult(bool(allowed), application_name, application_id,
                                          str(reason) if reason else None,
                                          checks if isinstance(checks, dict) else {}, source)

    def preflight_application(self, application: Any) -> CalibrationPreflightResult:
        application_info = self._resolve_application(application)
        if not application_info:
            return CalibrationPreflightResult(False, str(application), reason="Aplicaci\u00f3n no encontrada")
        name = application_info["name"]
        app_id = application_info.get("app_id", "")
        if self._should_ignore_application(name, app_id):
            return CalibrationPreflightResult(False, name, app_id,
                                              "La aplicaci\u00f3n est\u00e1 bloqueada para calibraci\u00f3n", {"internal_filters": True})
        if self._is_game_application(name, app_id):
            return CalibrationPreflightResult(False, name, app_id,
                                              "La aplicaci\u00f3n est\u00e1 clasificada como juego", {"game": True})
        if self._preflight_checker is None:
            return CalibrationPreflightResult(True, name, app_id,
                                              checks={"internal_filters": True, "external_preflight": False})
        try:
            return self._normalize_preflight_result(self._preflight_checker(application_info), application_info,
                                                    "application_preflight")
        except Exception as exc:
            logger.info("Procesando solicitud: " + str(exc))
            return CalibrationPreflightResult(False, name, app_id, f"Error durante preflight: {exc}",
                                              source="application_preflight")

    def get_application_calibration_capability(self, application: Any) -> Dict[str, Any]:
        result = self.preflight_application(application)
        return {
            "capability": "calibrate_application",
            "application": result.application_name,
            "application_id": result.application_id,
            "allowed": result.allowed,
            "reason": result.reason,
            "checks": dict(result.checks),
            "preflight_source": result.source,
        }

    # ========================================================================
    # METADATA / DESCUBRIMIENTO
    # ========================================================================

    def _reset_application_metadata_cache(self) -> None:
        self._application_metadata_by_name = {}
        self._application_metadata_by_app_id = {}
        self._application_metadata_all = []
        self._application_metadata_loaded = False

    @staticmethod
    def _normalize_filesystem_path(path: str) -> str:
        value = str(path or "").strip().strip('"').strip("'").replace("/", "\\")
        while "\\\\" in value:
            value = value.replace("\\\\", "\\")
        return value.casefold()

    @staticmethod
    def _normalize_executable_name(path: str) -> str:
        if not path:
            return ""
        try:
            return Path(path).name.casefold()
        except Exception:
            return str(path).rsplit("\\", 1)[-1].casefold()

    def _register_application_metadata(self, metadata: Dict[str, str]) -> None:
        name = str(metadata.get("name", "")).strip()
        app_id = str(metadata.get("app_id", "")).strip()
        path = str(metadata.get("path", "")).strip()
        arguments = str(metadata.get("arguments", "")).strip()
        if (not name and not app_id) or (not path and not arguments):
            return
        item = {"name": name, "app_id": app_id, "path": path, "arguments": arguments,
                "source": str(metadata.get("source", "")).strip()}
        self._application_metadata_all.append(item)
        normalized_name = self._normalize_application_name(name)
        normalized_id = self._normalize_application_name(app_id)
        if normalized_name:
            self._application_metadata_by_name.setdefault(normalized_name, []).append(item)
        if normalized_id:
            self._application_metadata_by_app_id.setdefault(normalized_id, []).append(item)

    def _load_application_installation_metadata(self) -> None:
        if self._application_metadata_loaded:
            return
        self._reset_application_metadata_cache()
        powershell_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = New-Object System.Collections.Generic.List[object]
# 3.8.1.4: el mecanismo por defecto de descubrimiento NO usa busqueda recursiva
# por todo el disco. Los accesos directos (.lnk) se leen solo a nivel raiz de las
# dos carpetas del Menu Inicio (APPDATA y ProgramData). Get-StartApps cubre el
# resto de aplicaciones del menu sin recorrer el disco.
$roots = @((Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
           (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))
try {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -Filter '*.lnk' -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            try {
                $shortcut = $shell.CreateShortcut($_.FullName)
                $result.Add([PSCustomObject]@{Source='start_menu';Name=$_.BaseName;AppID='';Path=[string]$shortcut.TargetPath;Arguments=[string]$shortcut.Arguments})
            } catch {}
        }
    }
} catch {}
try {
    Get-AppxPackage -AllUsers | Where-Object {$_.InstallLocation} |
    ForEach-Object {$result.Add([PSCustomObject]@{Source='appx';Name=[string]$_.Name;AppID=[string]$_.PackageFamilyName;Path=[string]$_.InstallLocation;Arguments=''})}
} catch {}
$registryRoots = @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
                   'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
                   'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')
foreach ($root in $registryRoots) {
    try {
        Get-ItemProperty $root | Where-Object {$_.DisplayName} | ForEach-Object {
            $path=''
            if ($_.InstallLocation) {$path=[string]$_.InstallLocation} elseif ($_.DisplayIcon) {$path=[string]$_.DisplayIcon}
            if ($path) {$result.Add([PSCustomObject]@{Source='uninstall_registry';Name=[string]$_.DisplayName;AppID='';Path=$path;Arguments=''})}
        }
    } catch {}
}
$result | ConvertTo-Json -Compress -Depth 4
"""
        try:
            process = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", powershell_script],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            if process.returncode != 0 or not process.stdout.strip():
                self._application_metadata_loaded = True
                return
            data = json.loads(process.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                self._application_metadata_loaded = True
                return
            for item in data:
                if isinstance(item, dict):
                    self._register_application_metadata({
                        "name": item.get("Name", ""), "app_id": item.get("AppID", ""),
                        "path": item.get("Path", ""), "arguments": item.get("Arguments", ""),
                        "source": item.get("Source", ""),
                    })
        except Exception as exc:
            logger.debug("CalibrationManager._load_application_installation_metadata: %s", exc)
        finally:
            self._application_metadata_loaded = True

    def _get_application_metadata(self, name: str, app_id: str = "") -> List[Dict[str, str]]:
        self._load_application_installation_metadata()
        result: List[Dict[str, str]] = []
        seen: Set[Tuple[str, str, str]] = set()
        for candidate in (*self._application_metadata_by_name.get(self._normalize_application_name(name), []),
                          *self._application_metadata_by_app_id.get(self._normalize_application_name(app_id), [])):
            key = (candidate.get("path", "").casefold(), candidate.get("arguments", "").casefold(),
                   candidate.get("source", "").casefold())
            if key not in seen:
                seen.add(key)
                result.append(candidate)
        return result

    def discover_applications(self) -> List[Dict[str, str]]:
        """Descubre aplicaciones GUI sin limitarse a una lista de apps conocidas."""
        logger.info(r"[CALIBRATION-MANAGER] Descubriendo aplicaciones instaladas...")
        self._load_application_installation_metadata()

        applications: List[Dict[str, str]] = []
        seen_names: Set[str] = set()
        seen_ids: Set[str] = set()

        def add_application(
            name: str,
            app_id: str = "",
            path: str = "",
            arguments: str = "",
        ) -> None:
            name = str(name or "").strip()
            app_id = str(app_id or "").strip()
            path = str(path or "").strip()
            arguments = str(arguments or "").strip()
            if not name or self._should_ignore_application(name, app_id):
                return

            storage_key = self._get_storage_application_key(name)
            normalized_id = app_id.casefold()
            if storage_key in seen_names or (normalized_id and normalized_id in seen_ids):
                return

            record: Dict[str, str] = {"name": name, "app_id": app_id}
            if path:
                record["path"] = path
            if arguments:
                record["arguments"] = arguments
            applications.append(record)
            seen_names.add(storage_key)
            if normalized_id:
                seen_ids.add(normalized_id)

        # 1) StartApps: preferidos cuando existe un AppID funcional.
        command = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
        )
        try:
            process = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if process.returncode == 0 and process.stdout.strip():
                data = json.loads(process.stdout.strip())
                if isinstance(data, dict):
                    data = [data]
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("Name", "")).strip()
                        app_id = str(item.get("AppID", "")).strip()
                        metadata = self._get_application_metadata(name, app_id)
                        path = next((str(m.get("path", "")).strip() for m in metadata if m.get("path")), "")
                        arguments = next((str(m.get("arguments", "")).strip() for m in metadata if m.get("arguments")), "")
                        add_application(name, app_id, path, arguments)
        except Exception as exc:
            logger.debug("CalibrationManager.discover_applications: %s", exc)

        # 2) Metadatos de accesos directos, AppX y desinstaladores.
        #    Esto permite descubrir aplicaciones GUI que no aparecen en Get-StartApps.
        for item in self._application_metadata_all:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            path = str(item.get("path", "")).strip()
            app_id = str(item.get("app_id", "")).strip()
            arguments = str(item.get("arguments", "")).strip()
            if not name or not path or not os.path.isfile(path):
                continue
            add_application(name, app_id, path, arguments)

        applications.sort(key=lambda item: (item["name"].casefold(), item.get("app_id", "").casefold()))
        logger.info(f"Procesadas {len(applications)} aplicaciones GUI")
        return applications

    # ========================================================================
    # REPORTE DE FUENTES DE DESCUBRIMIENTO (3.8.1.5)
    # ========================================================================

    def get_discovery_source_report(self) -> Dict[str, Any]:
        """Registra cobertura, permisos y limitaciones de cada fuente de
        descubrimiento de aplicaciones.

        Retorna un diccionario con una entrada por fuente, cada una con:
        source, ok, count, samples, error, coverage, permissions, limitations.

        Es de lectura sola: no lanza, no instala ni modifica ninguna aplicacion.
        """
        report: Dict[str, Any] = {}

        # 1) Aplicaciones instaladas (mecanismo real de CalibrationManager)
        try:
            apps = self.discover_applications() or []
            by_source: Dict[str, int] = {}
            for app in apps:
                src = str(app.get("source", "desconocido"))
                by_source[src] = by_source.get(src, 0) + 1
            samples = [
                {
                    "name": app.get("name", ""),
                    "app_id": app.get("app_id", "") or "",
                    "path": app.get("path", "") or "",
                    "source": app.get("source", "") or "",
                }
                for app in apps[:12]
            ]
            report["aplicaciones_instaladas"] = {
                "source": "aplicaciones_instaladas",
                "ok": True,
                "count": len(apps),
                "samples": samples,
                "error": None,
                "coverage": (
                    "Get-StartApps (menu Inicio con AppID), accesos directos .lnk del "
                    "menu Inicio (APPDATA y ProgramData, nivel raiz sin recursion por "
                    "disco, cumple 3.8.1.4), paquetes AppX (Get-AppxPackage -AllUsers) "
                    "y registro de desinstaladores (HKCU/HKLM/WOW6432Node Uninstall)."
                ),
                "permissions": (
                    "Ejecucion de PowerShell (ExecutionPolicy Bypass), lectura de "
                    "sistema de archivos (accesos directos .lnk), lectura de registro "
                    "de Windows (desinstaladores y paquetes AppX)."
                ),
                "limitations": (
                    "Filtrado por _should_ignore_application; los metadatos de "
                    "desinstalador/shortcut solo se anaden si el path existe en disco "
                    "(os.path.isfile); fuentes sin path usable quedan excluidas; no se "
                    "usa busqueda recursiva por todo el disco como mecanismo por defecto "
                    "(3.8.1.4)."
                ),
                "by_source": by_source,
            }
        except Exception as exc:
            report["aplicaciones_instaladas"] = {
                "source": "aplicaciones_instaladas",
                "ok": False,
                "count": 0,
                "samples": [],
                "error": f"{type(exc).__name__}: {exc}",
                "coverage": "Get-StartApps, .lnk menu Inicio, AppX, registro de desinstaladores",
                "permissions": "Ejecucion de PowerShell, lectura de sistema de archivos y registro",
                "limitations": "Fuente no disponible por error de ejecucion",
            }

        # 2) Rutas registradas en PATH
        try:
            raw_path = os.environ.get("PATH", "")
            dirs = [d for d in raw_path.split(os.pathsep) if d]
            existing = [d for d in dirs if os.path.isdir(d)]
            missing = [d for d in dirs if not os.path.isdir(d)]
            exe_samples: List[str] = []
            for directory in existing:
                try:
                    for entry in os.listdir(directory):
                        if entry.lower().endswith(".exe") and len(exe_samples) < 40:
                            exe_samples.append(entry)
                except (OSError, PermissionError):
                    continue
            report["rutas_registradas_path"] = {
                "source": "rutas_registradas_path",
                "ok": True,
                "count": len(dirs),
                "samples": {
                    "total_dirs": len(dirs),
                    "existing_dirs": len(existing),
                    "missing_dirs": len(missing),
                    "exe_sample": sorted(set(exe_samples))[:12],
                },
                "error": None,
                "coverage": "Variable de entorno PATH del usuario/proceso actual.",
                "permissions": "Lectura de variable de entorno PATH y listado de directorios del sistema de archivos.",
                "limitations": (
                    "Solo se inspecciona la primera capa de cada carpeta PATH; no se "
                    "hace busqueda recursiva por el disco (evitado por diseno, 3.8.1.4)."
                ),
            }
        except Exception as exc:
            report["rutas_registradas_path"] = {
                "source": "rutas_registradas_path",
                "ok": False,
                "count": 0,
                "samples": {},
                "error": f"{type(exc).__name__}: {exc}",
                "coverage": "Variable de entorno PATH",
                "permissions": "Lectura de variable de entorno",
                "limitations": "Fuente no disponible por error de ejecucion",
            }

        # 3) Rutas registradas en App Paths del registro de Windows
        try:
            import winreg
            _APP_PATHS_ROOTS = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            ]
            entries: List[Dict[str, str]] = []
            errors: List[str] = []
            for hive, root in _APP_PATHS_ROOTS:
                try:
                    with winreg.OpenKey(hive, root) as key:
                        index = 0
                        while True:
                            try:
                                exe_name = winreg.EnumKey(key, index)
                            except OSError:
                                break
                            index += 1
                            try:
                                with winreg.OpenKey(key, exe_name) as subkey:
                                    path, _ = winreg.QueryValueEx(subkey, "")
                                    exe_path, _ = winreg.QueryValueEx(subkey, "Path")
                            except OSError:
                                path = ""
                                exe_path = ""
                            entries.append(
                                {
                                    "hive": "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM",
                                    "exe": exe_name,
                                    "path": path,
                                    "path_env": exe_path,
                                }
                            )
                except OSError as exc:
                    errors.append(f"{root}: {type(exc).__name__}: {exc}")
            report["rutas_registradas_app_paths"] = {
                "source": "rutas_registradas_app_paths",
                "ok": len(errors) == 0,
                "count": len(entries),
                "samples": entries[:12],
                "error": "; ".join(errors) if errors else None,
                "coverage": "HKCU y HKLM Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\App Paths\\\\*",
                "permissions": "Lectura de claves de registro HKCU y HKLM (App Paths).",
                "limitations": (
                    "Cada entrada es un ejecutable concreto registrado por instalador; no "
                    "cubre aplicaciones sin registro en App Paths."
                ),
            }
        except Exception as exc:
            report["rutas_registradas_app_paths"] = {
                "source": "rutas_registradas_app_paths",
                "ok": False,
                "count": 0,
                "samples": [],
                "error": f"{type(exc).__name__}: {exc}",
                "coverage": "Registro de Windows App Paths",
                "permissions": "Lectura de registro HKCU/HKLM",
                "limitations": "Fuente no disponible por error de ejecucion",
            }

        # 4) Procesos activos
        try:
            processes: List[Dict[str, Any]] = []
            try:
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, check=False, timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().splitlines():
                        parts = [p.strip('"') for p in line.split('","')]
                        if len(parts) >= 2:
                            processes.append({"pid": parts[1], "name": parts[0]})
                            if len(processes) >= 60:
                                break
            except (OSError, subprocess.SubprocessError):
                pass
            report["procesos_activos"] = {
                "source": "procesos_activos",
                "ok": True,
                "count": len(processes),
                "samples": processes[:12],
                "error": None,
                "coverage": "tasklist (Windows) sobre procesos visibles al proceso actual.",
                "permissions": "Enumeracion de procesos del sistema (tasklist).",
                "limitations": (
                    "Puede no incluir procesos del sistema sin privilegios elevados; "
                    "el PID/name proviene de tasklist y puede carecer de detalles de sesion."
                ),
            }
        except Exception as exc:
            report["procesos_activos"] = {
                "source": "procesos_activos",
                "ok": False,
                "count": 0,
                "samples": [],
                "error": f"{type(exc).__name__}: {exc}",
                "coverage": "Procesos activos del sistema",
                "permissions": "Enumeracion de procesos",
                "limitations": "Fuente no disponible por error de ejecucion",
            }

        # 5) Ventanas activas
        try:
            windows = gw.getAllWindows() or []
            foreground = gw.getActiveWindow()
            samples = [
                {"title": w.title, "pid": getattr(w, "_pid", None)}
                for w in windows[:12]
            ]
            report["ventanas_activas"] = {
                "source": "ventanas_activas",
                "ok": True,
                "count": len(windows),
                "samples": samples,
                "error": None,
                "coverage": "pygetwindow.getAllWindows + getActiveWindow (ventana foreground).",
                "permissions": "Enumeracion de ventanas de escritorio (pygetwindow / Win32 user32).",
                "limitations": (
                    "Titulos pueden estar vacios para ventanas sin titulo o inaccesibles; "
                    "no se lanza ninguna aplicacion; ventana foreground puede ser None."
                ),
                "foreground_title": foreground.title if foreground else None,
            }
        except Exception as exc:
            report["ventanas_activas"] = {
                "source": "ventanas_activas",
                "ok": False,
                "count": 0,
                "samples": [],
                "error": f"{type(exc).__name__}: {exc}",
                "coverage": "Ventanas activas del escritorio",
                "permissions": "Enumeracion de ventanas",
                "limitations": "Fuente no disponible por error de ejecucion",
            }

        return report

    # ========================================================================
    # FILTROS
    # ========================================================================

    def _is_vscode_application(self, name: str, app_id: str = "") -> bool:
        normalized_name = self._normalize_application_name(name)
        normalized_id = self._normalize_application_name(app_id)
        if normalized_name in {self._normalize_application_name(x) for x in self.VSCODE_EXACT_NAMES}:
            return True
        if any(self._normalize_application_name(x) in normalized_name for x in self.VSCODE_NAME_PARTS):
            return True
        if "visualstudiocode" in normalized_id or normalized_id in {"code", "code_insiders"}:
            return True
        for item in self._get_application_metadata(name, app_id):
            executable = self._normalize_executable_name(item.get("path", ""))
            normalized_path = self._normalize_filesystem_path(item.get("path", ""))
            if executable in self.VSCODE_EXECUTABLES or any(part in normalized_path for part in self.VSCODE_PATH_PARTS):
                return True
        return False

    def _is_game_launcher_application(self, name: str, app_id: str = "") -> bool:
        normalized = self._normalize_application_name(name)
        exact = {self._normalize_application_name(x) for x in self.GAME_LAUNCHER_EXACT_NAMES}
        return normalized in exact or any(self._normalize_application_name(x) in normalized for x in self.GAME_LAUNCHER_NAME_PARTS)

    def _is_game_launcher_executable(self, path: str) -> bool:
        return self._normalize_executable_name(path) in {x.casefold() for x in self.GAME_LAUNCHER_EXECUTABLES}

    def _looks_like_game_launch_arguments(self, name: str, arguments: str) -> bool:
        if not arguments or self._is_game_launcher_application(name):
            return False
        normalized = str(arguments).casefold()
        return any(token in normalized for token in self.GAME_LAUNCH_ARGUMENT_PARTS)

    def _is_game_installation_path(self, path: str) -> bool:
        normalized = self._normalize_filesystem_path(path)
        if not normalized or self._is_game_launcher_executable(normalized):
            return False
        if any(pattern in normalized for pattern in self.GAME_INSTALL_PATH_PARTS):
            return True
        if any(pattern in normalized for pattern in self.GAME_RIOT_INSTALL_PATH_PARTS):
            return True
        for pattern in self.GAME_INSTALL_ROOT_PARTS:
            if pattern in normalized and "\\epic games\\launcher\\" not in normalized:
                return True
        return False

    def _is_game_application(self, name: str, app_id: str = "") -> bool:
        normalized_name = self._normalize_application_name(name)
        normalized_id = self._normalize_application_name(app_id)
        if not normalized_name or self._is_game_launcher_application(name, app_id):
            return False
        if self.GAME_STEAM_APP_ID_PATTERN.fullmatch(app_id.strip()) or any(self._normalize_application_name(x) in normalized_name for x in self.GAME_NAME_PARTS):
            return True
        if normalized_name in {self._normalize_application_name(x) for x in self.GAME_EXACT_NAMES}:
            return True
        if any(self._normalize_application_name(x) in normalized_id for x in self.GAME_APP_ID_PARTS):
            return True
        for item in self._get_application_metadata(name, app_id):
            if self._is_game_launcher_executable(item.get("path", "")):
                continue
            if self._looks_like_game_launch_arguments(name, item.get("arguments", "")):
                return True
            if item.get("path") and self._is_game_installation_path(item["path"]):
                return True
        return False

    def _is_elevation_risk_application(self, name: str, app_id: str = "") -> bool:
        normalized = self._normalize_application_name(name)
        exact = {self._normalize_application_name(x) for x in self.ELEVATION_RISK_EXACT_NAMES}
        if normalized in exact or any(self._normalize_application_name(x) in normalized for x in self.ELEVATION_RISK_NAME_PARTS):
            return True
        normalized_id = self._normalize_application_name(app_id)
        return any(token in normalized_id for token in (
            "application_verifier", "verifier", "admin", "elevated", "systemtools", "security_policy",
            "task_scheduler", "computer_management", "registry", "hyper_v", "event_viewer", "services", "firewall",
        ))

    @staticmethod
    def _looks_like_console_or_cli_launcher(normalized_name: str) -> bool:
        if not normalized_name:
            return True
        protected_console_names = {"powershell", "powershell_x86", "windows_powershell", "windows_powershell_x86", "git_bash", "git_cmd", "node_js_command_prompt"}
        if normalized_name in protected_console_names:
            return True
        if re.fullmatch(r"python_\d+(?:_\d+)?(?:_64_bit)?", normalized_name):
            return True
        return any(token in normalized_name for token in ("manuals", "module_docs", "documentation", "native_tools_command_prompt", "cross_tools_command_prompt")) or normalized_name.endswith("_powershell") or normalized_name.endswith("_command_prompt")

    def _should_ignore_application(self, name: str, app_id: str = "") -> bool:
        normalized_name = self._normalize_application_name(name)
        normalized_id = self._normalize_application_name(app_id)
        if not normalized_name:
            return True
        if self._is_vscode_application(name, app_id):
            return True
        if normalized_name in {self._normalize_application_name(x) for x in self.ALLOWED_WINDOWS_GUI_NAMES}:
            return False
        if self._is_elevation_risk_application(name, app_id) or self._is_game_application(name, app_id):
            return True
        if normalized_name in {self._normalize_application_name(x) for x in self.IGNORED_EXACT_NAMES}:
            return True
        if any(self._normalize_application_name(x) in normalized_name for x in self.IGNORED_NAME_PARTS):
            return True
        if normalized_id and any(token in normalized_id for token in ("help", "documentation", "documentacion", "manual", "readme", "sample", "tutorial", "uninstall", "support", "website", "docs")):
            return True
        return name.strip().startswith(".") or self._looks_like_console_or_cli_launcher(normalized_name)

    # ========================================================================
    # VENTANAS / PROCESOS
    # ========================================================================

    def _get_windows(self) -> List[Any]:
        try:
            return list(gw.getAllWindows())
        except Exception:
            return []

    @staticmethod
    def _get_window_handle(window: Any) -> Optional[int]:
        if window is None:
            return None
        if isinstance(window, int):
            return int(window)
        for attr in ("_hWnd", "_hwnd", "hwnd"):
            value = getattr(window, attr, None)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
        return None

    def _get_window_handles(self) -> Set[int]:
        return {h for h in (self._get_window_handle(w) for w in self._get_windows()) if h is not None}

    @staticmethod
    def _win32_is_window(hwnd: Optional[int]) -> bool:
        if not hwnd:
            return False
        try:
            return bool(USER32.IsWindow(wintypes.HWND(hwnd)))
        except Exception:
            return False

    @staticmethod
    def _win32_is_visible(hwnd: Optional[int]) -> bool:
        if not hwnd:
            return False
        try:
            return bool(USER32.IsWindowVisible(wintypes.HWND(hwnd)))
        except Exception:
            return False

    @staticmethod
    def _win32_is_enabled(hwnd: Optional[int]) -> bool:
        if not hwnd:
            return False
        try:
            return bool(USER32.IsWindowEnabled(wintypes.HWND(hwnd)))
        except Exception:
            return False

    @staticmethod
    def _win32_get_class_name(hwnd: Optional[int]) -> str:
        if not hwnd:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(256)
            result = USER32.GetClassNameW(wintypes.HWND(hwnd), buffer, len(buffer))
            return buffer.value.strip() if result > 0 else ""
        except Exception:
            return ""

    @staticmethod
    def _win32_get_window_title(hwnd: Optional[int]) -> str:
        if not hwnd:
            return ""
        try:
            length = int(USER32.GetWindowTextLengthW(wintypes.HWND(hwnd)))
            if length <= 0:
                return ""
            buffer = ctypes.create_unicode_buffer(length + 1)
            USER32.GetWindowTextW(wintypes.HWND(hwnd), buffer, length + 1)
            return buffer.value.strip()
        except Exception:
            return ""

    @staticmethod
    def _win32_get_window_rect(hwnd: Optional[int]) -> Optional[Tuple[int, int, int, int]]:
        if not hwnd:
            return None
        rect = wintypes.RECT()
        try:
            if not USER32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
                return None
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        except Exception:
            return None

    @staticmethod
    def _win32_get_owner(hwnd: Optional[int]) -> Optional[int]:
        if not hwnd:
            return None
        try:
            owner = USER32.GetWindow(wintypes.HWND(hwnd), GW_OWNER)
            return int(owner) if owner else None
        except Exception:
            return None

    @staticmethod
    def _win32_get_style(hwnd: Optional[int]) -> int:
        if not hwnd:
            return 0
        try:
            return int(USER32.GetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE)) & 0xFFFFFFFF
        except Exception:
            return 0

    @staticmethod
    def _win32_get_exstyle(hwnd: Optional[int]) -> int:
        if not hwnd:
            return 0
        try:
            return int(USER32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)) & 0xFFFFFFFF
        except Exception:
            return 0

    @classmethod
    def _win32_is_gui_window(
        cls, hwnd: Optional[int], allow_console: bool = False
    ) -> bool:
        if (
            not hwnd
            or not cls._win32_is_window(hwnd)
            or not cls._win32_is_visible(hwnd)
            or not cls._win32_is_enabled(hwnd)
        ):
            return False
        if cls._win32_get_owner(hwnd):
            return False
        if not (cls._win32_get_style(hwnd) & WS_VISIBLE):
            return False
        exstyle = cls._win32_get_exstyle(hwnd)
        if exstyle & WS_EX_TOOLWINDOW or exstyle & WS_EX_NOACTIVATE:
            return False
        if (
            not allow_console
            and cls._win32_get_class_name(hwnd).casefold() in cls.NON_GUI_WINDOW_CLASSES
        ):
            return False

        # Una ventana minimizada puede tener un GetWindowRect reducido o no
        # representativo. Para decidir si sigue siendo una ventana GUI valida,
        # usamos su rcNormalPosition en ese caso.
        try:
            is_minimized = bool(USER32.IsIconic(wintypes.HWND(hwnd)))
        except Exception:
            is_minimized = False

        if is_minimized:
            try:
                placement = WINDOWPLACEMENT()
                placement.length = ctypes.sizeof(WINDOWPLACEMENT)
                if USER32.GetWindowPlacement(
                    wintypes.HWND(hwnd),
                    ctypes.byref(placement),
                ):
                    normal = placement.rcNormalPosition
                    width = int(normal.right) - int(normal.left)
                    height = int(normal.bottom) - int(normal.top)
                    return width >= cls.MIN_GUI_WIDTH and height >= cls.MIN_GUI_HEIGHT
            except Exception:
                pass

        rect = cls._win32_get_window_rect(hwnd)
        if rect is None:
            return False
        left, top, right, bottom = rect
        return (right - left) >= cls.MIN_GUI_WIDTH and (bottom - top) >= cls.MIN_GUI_HEIGHT

    @classmethod
    def _window_is_usable(
        cls, window: Any, allow_console: bool = False
    ) -> bool:
        hwnd = cls._get_window_handle(window)
        if hwnd:
            return cls._win32_is_gui_window(hwnd, allow_console=allow_console)
        try:
            return (
                bool(getattr(window, "visible", True))
                and int(getattr(window, "width", 0) or 0) >= cls.MIN_GUI_WIDTH
                and int(getattr(window, "height", 0) or 0) >= cls.MIN_GUI_HEIGHT
            )
        except Exception:
            return False

    @staticmethod
    def _get_window_geometry(
        window: Any,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Devuelve geometria utilizable incluso cuando la ventana esta minimizada."""
        hwnd = CalibrationManager._get_window_handle(window)
        if hwnd:
            try:
                placement = WINDOWPLACEMENT()
                placement.length = ctypes.sizeof(WINDOWPLACEMENT)
                if USER32.GetWindowPlacement(
                    wintypes.HWND(hwnd), ctypes.byref(placement)
                ):
                    normal = placement.rcNormalPosition
                    width = int(normal.right) - int(normal.left)
                    height = int(normal.bottom) - int(normal.top)
                    is_minimized = placement.showCmd == 2
                    try:
                        is_minimized = bool(
                            is_minimized or USER32.IsIconic(wintypes.HWND(hwnd))
                        )
                    except Exception:
                        pass
                    if is_minimized and width > 0 and height > 0:
                        return int(normal.left), int(normal.top), width, height
            except Exception as exc:
                logger.debug("CalibrationManager._get_window_geometry: %s", exc)
            rect = CalibrationManager._win32_get_window_rect(hwnd)
            if rect is not None:
                left, top, right, bottom = rect
                return left, top, max(1, right - left), max(1, bottom - top)
        try:
            return (
                int(getattr(window, "left")),
                int(getattr(window, "top")),
                max(1, int(getattr(window, "width"))),
                max(1, int(getattr(window, "height"))),
            )
        except Exception:
            return None

    @staticmethod
    def _capture_window_state(
        hwnd: Optional[int],
    ) -> Optional[_WindowStateSnapshot]:
        if not hwnd:
            return None
        try:
            placement = WINDOWPLACEMENT()
            placement.length = ctypes.sizeof(WINDOWPLACEMENT)
            if not USER32.GetWindowPlacement(
                wintypes.HWND(hwnd), ctypes.byref(placement)
            ):
                return None
            normal = placement.rcNormalPosition
            return _WindowStateSnapshot(
                flags=int(placement.flags),
                show_cmd=int(placement.showCmd),
                min_x=int(placement.ptMinPosition.x),
                min_y=int(placement.ptMinPosition.y),
                max_x=int(placement.ptMaxPosition.x),
                max_y=int(placement.ptMaxPosition.y),
                normal_left=int(normal.left),
                normal_top=int(normal.top),
                normal_right=int(normal.right),
                normal_bottom=int(normal.bottom),
            )
        except Exception:
            return None

    @staticmethod
    def _restore_window_state(
        hwnd: Optional[int],
        snapshot: Optional[_WindowStateSnapshot],
    ) -> bool:
        if (
            not hwnd
            or snapshot is None
            or not USER32.IsWindow(wintypes.HWND(hwnd))
        ):
            return False
        try:
            placement = WINDOWPLACEMENT()
            placement.length = ctypes.sizeof(WINDOWPLACEMENT)
            placement.flags = snapshot.flags
            placement.showCmd = snapshot.show_cmd
            placement.ptMinPosition = wintypes.POINT(
                snapshot.min_x, snapshot.min_y
            )
            placement.ptMaxPosition = wintypes.POINT(
                snapshot.max_x, snapshot.max_y
            )
            placement.rcNormalPosition = wintypes.RECT(
                snapshot.normal_left,
                snapshot.normal_top,
                snapshot.normal_right,
                snapshot.normal_bottom,
            )
            return bool(
                USER32.SetWindowPlacement(
                    wintypes.HWND(hwnd), ctypes.byref(placement)
                )
            )
        except Exception:
            return False

    def _get_window_by_handle(self, hwnd: int) -> Any:
        for window in self._get_windows():
            if self._get_window_handle(window) == hwnd:
                return window
        return None

    @staticmethod
    def _get_window_process_id(window: Any) -> Optional[int]:
        hwnd = CalibrationManager._get_window_handle(window)
        if not hwnd:
            return None
        try:
            pid = wintypes.DWORD()
            result = USER32.GetWindowThreadProcessId(
                wintypes.HWND(hwnd), ctypes.byref(pid)
            )
            return int(pid.value) if result and pid.value else None
        except Exception:
            return None

    @classmethod
    def _get_window_process_name(cls, window: Any) -> str:
        pid = cls._get_window_process_id(window)
        if pid is None:
            return ""
        try:
            import psutil
            return str(psutil.Process(pid).name() or "")
        except Exception:
            return ""

    @staticmethod
    def _get_process_ids() -> Set[int]:
        try:
            import psutil
            return {int(pid) for pid in psutil.pids()}
        except Exception:
            return set()

    @staticmethod
    def _get_process_tree(
        root_pid: Optional[int], before_pids: Optional[Set[int]] = None
    ) -> Set[int]:
        if not root_pid:
            return set()
        before = before_pids or set()
        owned: Set[int] = set()
        try:
            import psutil
            root = psutil.Process(int(root_pid))
            if root.pid not in before:
                owned.add(root.pid)
            for child in root.children(recursive=True):
                if child.pid not in before:
                    owned.add(int(child.pid))
        except Exception:
            if int(root_pid) not in before:
                owned.add(int(root_pid))
        return owned

    @staticmethod
    def _is_process_alive(pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            import psutil
            return bool(psutil.pid_exists(int(pid)))
        except Exception:
            return False

    @staticmethod
    def _is_process_elevated(pid: Optional[int]) -> bool:
        if not pid:
            return False
        process_handle = None
        token_handle = wintypes.HANDLE()
        try:
            process_handle = KERNEL32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not process_handle:
                return False
            if not ADVAPI32.OpenProcessToken(
                wintypes.HANDLE(process_handle),
                TOKEN_QUERY,
                ctypes.byref(token_handle),
            ):
                return False
            elevation = wintypes.DWORD()
            returned = wintypes.DWORD()
            if not ADVAPI32.GetTokenInformation(
                token_handle,
                TOKEN_INFORMATION_CLASS_ELEVATION,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                ctypes.byref(returned),
            ):
                return False
            return bool(elevation.value)
        except Exception:
            return False
        finally:
            try:
                if token_handle:
                    KERNEL32.CloseHandle(token_handle)
            except Exception:
                pass
            try:
                if process_handle:
                    KERNEL32.CloseHandle(process_handle)
            except Exception:
                pass

    def _expected_process_names(self, application_name: str, app_id: str = "") -> Set[str]:
        """Obtiene nombres de proceso esperados para una aplicacion."""
        normalized = self._normalize_application_name(application_name)
        expected: Set[str] = set()
        builtins = {
            "chrome": {"chrome.exe"},
            "edge": {"msedge.exe"},
            "firefox": {"firefox.exe"},
            "spotify": {"spotify.exe"},
            "notepad": {"notepad.exe"},
            "bloc_de_notas": {"notepad.exe"},
            "calculator": {"calculatorapp.exe", "calc.exe"},
            "calculadora": {"calculatorapp.exe", "calc.exe"},
            "paint": {"mspaint.exe"},
            "explorer": {"explorer.exe"},
            "explorador_de_archivos": {"explorer.exe"},
            "cmd": {"cmd.exe"},
            "command_prompt": {"cmd.exe"},
        }
        expected.update(name.casefold() for name in builtins.get(normalized, set()))
        for metadata in self._get_application_metadata(application_name, app_id):
            executable = self._normalize_executable_name(metadata.get("path", ""))
            if executable and executable.endswith(".exe"):
                expected.add(executable.casefold())
        return expected

    def _score_window_for_application(
        self, window: Any, application_name: str, app_id: str = ""
    ) -> int:
        normalized_app = self._normalize_application_name(application_name)
        allow_console = self._get_application_type(application_name) == ApplicationType.CMD
        if not self._window_is_usable(window, allow_console=allow_console):
            return -1

        hwnd = self._get_window_handle(window)
        title = self._win32_get_window_title(hwnd) or str(getattr(window, "title", "") or "")
        normalized_title = self._normalize_application_name(title)
        process_name = self._get_window_process_name(window).casefold()
        normalized_process = self._normalize_application_name(process_name)
        normalized_id = self._normalize_application_name(app_id)

        expected_processes = self._expected_process_names(application_name, app_id)
        if expected_processes and process_name and process_name not in expected_processes:
            # Si conocemos el ejecutable real de la aplicacion, no confundimos
            # ventanas de otro proceso basado unicamente en el titulo.
            return -1

        app_tokens = {t for t in normalized_app.split("_") if len(t) >= 3}
        title_tokens = {t for t in normalized_title.split("_") if len(t) >= 3}
        process_tokens = {t for t in normalized_process.split("_") if len(t) >= 3}
        id_tokens = {t for t in normalized_id.split("_") if len(t) >= 3}

        score = 0
        if process_name in expected_processes:
            score += 300
        if normalized_title == normalized_app:
            score += 120
        if normalized_app and normalized_app in normalized_title:
            score += 90
        if normalized_title and normalized_title in normalized_app:
            score += 70
        score += 25 * len(app_tokens & title_tokens)
        score += 60 * len(app_tokens & process_tokens)
        score += 35 * len(app_tokens & id_tokens)
        if normalized_process and normalized_process in normalized_id:
            score += 50

        geometry = self._get_window_geometry(window)
        if geometry:
            _, _, width, height = geometry
            area = max(0, width) * max(0, height)
            if area >= 500_000:
                score += 20
            elif area >= 200_000:
                score += 10

        try:
            if bool(getattr(window, "isActive", False)):
                score += 10
        except Exception:
            pass
        return score

    def _find_existing_application_window(
        self, application_name: str, app_id: str = ""
    ) -> Any:
        candidates: List[Tuple[int, Any]] = []
        for window in self._get_windows():
            score = self._score_window_for_application(
                window, application_name, app_id
            )
            if score >= 0:
                candidates.append((score, window))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1] if candidates and candidates[0][0] >= 50 else None

    # ========================================================================
    # APERTURA / PREPARACION
    # ========================================================================

    def _reset_launch_context(self) -> None:
        self._last_launch_before_hwnds = set()
        self._last_launch_before_pids = set()
        self._last_launch_owned_hwnds = set()
        self._last_launch_owned_pids = set()
        self._last_launch_window = None
        self._last_launch_was_owned = False
        self._last_launch_root_pid = None
        self._last_launch_state = None
        self._last_launch_tipo_destino = None
        self._last_launch_fuente = ""
        self._last_launch_destino_validado = None
        self._last_launch_timestamps = {}
        self._last_launch_window_info = {}
        self._last_launch_evidence_path = None
        self._temporary_browser_tab_open = False
        self._temporary_browser_hwnd = None

    def get_launch_state(self) -> Optional[LaunchState]:
        """Devuelve el ultimo estado de lanzamiento registrado (LaunchState o None)."""
        return self._last_launch_state

    def launch_application(self, application: Dict[str, str]) -> Tuple[Set[int], bool]:
        """Reutiliza una ventana existente o lanza la aplicacion de forma generica."""
        app_name = str(application.get("name", "")).strip()
        app_id = str(application.get("app_id", "")).strip()
        executable = str(application.get("path", application.get("executable", ""))).strip()
        arguments = str(application.get("arguments", "")).strip()
        self._reset_launch_context()
        self._last_launch_executable_path = executable or None
        self._last_launch_app_id = app_id
        self._last_launch_state = LaunchState.ABRIENDO
        self._last_launch_timestamps = {"inicio": time.time()}

        if (
            not app_name
            or self._should_ignore_application(app_name, app_id)
            or self._is_game_application(app_name, app_id)
        ):
            self._last_launch_state = LaunchState.FALLO
            return set(), False

        existing_window = self._find_existing_application_window(app_name, app_id)
        if existing_window is not None:
            hwnd = self._get_window_handle(existing_window)
            pid = self._get_window_process_id(existing_window)
            if hwnd and not self._is_process_elevated(pid):
                self._last_launch_before_hwnds = self._get_window_handles()
                self._last_launch_before_pids = self._get_process_ids()
                self._last_launch_window = existing_window
                self._last_launch_root_pid = pid
                self._last_launch_was_owned = False
                self._last_launch_state = LaunchState.ABIERTA_VERIFICADA
                state = "minimizada" if USER32.IsIconic(wintypes.HWND(hwnd)) else "visible"
                return set(self._last_launch_before_hwnds), True

        before_hwnds = self._get_window_handles()
        before_pids = self._get_process_ids()
        self._last_launch_before_hwnds = set(before_hwnds)
        self._last_launch_before_pids = set(before_pids)

        # Clasificar tipo de destino, fuente y destino validado antes de lanzar.
        if app_id:
            self._last_launch_tipo_destino = "paquete"
            self._last_launch_fuente = "shell_apps_folder"
            self._last_launch_destino_validado = app_id or None
        elif executable and os.path.isfile(executable):
            self._last_launch_tipo_destino = "ejecutable"
            self._last_launch_fuente = "ruta_directa"
            self._last_launch_destino_validado = executable
        else:
            self._last_launch_tipo_destino = None
            self._last_launch_fuente = "metadatos_descubrimiento"
            self._last_launch_destino_validado = None

        try:
            if app_id:
                command = ["explorer.exe", f"shell:AppsFolder\\{app_id}"]
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif executable and os.path.isfile(executable):
                command = [executable]
                if arguments:
                    command.extend(shlex.split(arguments, posix=False))
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                metadata = self._get_application_metadata(app_name, app_id)
                launched = False
                for item in metadata:
                    path = str(item.get("path", "")).strip()
                    if not path or not os.path.isfile(path):
                        continue
                    self._last_launch_destino_validado = path
                    fuente_item = str(item.get("source", "")).strip()
                    self._last_launch_fuente = fuente_item or "metadatos_descubrimiento"
                    self._last_launch_tipo_destino = self._clasificar_tipo_destino_por_ruta(path)
                    command = [path]
                    item_args = str(item.get("arguments", "")).strip()
                    if item_args:
                        command.extend(shlex.split(item_args, posix=False))
                    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    launched = True
                    break
                if not launched:
                    self._last_launch_state = LaunchState.FALLO
                    return before_hwnds, False

            window = self._wait_for_application_window(app_name, app_id, before_hwnds, before_pids)
            if window is None:
                self._last_launch_state = LaunchState.FALLO
                return before_hwnds, False

            self._last_launch_timestamps["ventana_detectada"] = time.time()
            hwnd = self._get_window_handle(window)
            self._last_launch_window_info = {"hwnd": hwnd}
            pid = self._get_window_process_id(window)
            if hwnd is None:
                self._last_launch_state = LaunchState.FALLO
                return before_hwnds, False

            is_new_window = hwnd not in before_hwnds
            is_new_process = pid is not None and pid not in before_pids
            owned_hwnds = {hwnd} if is_new_window else set()
            owned_pids = self._get_process_tree(pid, before_pids) if is_new_process else set()
            self._last_launch_owned_hwnds = set(owned_hwnds)
            self._last_launch_owned_pids = set(owned_pids)
            self._last_launch_window = window
            self._last_launch_was_owned = is_new_window or is_new_process
            self._last_launch_root_pid = pid
            self._last_launch_state = LaunchState.PROCESO_INICIADO

            if self._is_process_elevated(pid):
                self._last_launch_state = LaunchState.FALLO
                if owned_hwnds:
                    self._close_all_owned_windows(window, owned_hwnds, owned_pids)
                return before_hwnds, False

            logger.info(f"Aplicacion lanzada: {app_name} | HWND={hwnd} | PID={pid} | owned={self._last_launch_was_owned}")
            return before_hwnds, True
        except Exception as exc:
            self._last_launch_state = LaunchState.FALLO
            logger.debug("CalibrationManager.launch_application: %s", exc)
            return before_hwnds, False

    def verify_launch_process_stability(
        self,
        pid: Optional[int] = None,
        stability_interval: float = 2.0,
        stability_checks: int = 3,
    ) -> Dict[str, Any]:
        """Verifica que un proceso exista y siga vivo durante un intervalo acotado.

        Comprueba el PID inmediatamente y repite la comprobacion a lo largo del
        intervalo para evitar declarar exito a un proceso que se cierra al
        instante. Correlaciona con la ruta ejecutable y el app_id del ultimo
        lanzamiento cuando estan disponibles.

        Args:
            pid: PID a verificar. Si es None, usa el _last_launch_root_pid.
            stability_interval: Intervalo total en segundos para las comprobaciones.
            stability_checks: Numero de comprobaciones dentro del intervalo.

        Returns:
            Dict con claves: alive, pid, stable, checks_passed, total_checks,
            executable_path, app_id, was_owned, error.
        """
        target_pid = int(pid) if pid is not None else self._last_launch_root_pid
        if not target_pid:
            return {
                "alive": False,
                "pid": None,
                "stable": False,
                "checks_passed": 0,
                "total_checks": 0,
                "executable_path": self._last_launch_executable_path,
                "app_id": self._last_launch_app_id,
                "was_owned": self._last_launch_was_owned,
                "error": "No hay PID para verificar",
            }

        total_checks = max(1, int(stability_checks))
        delay = max(0.1, float(stability_interval) / total_checks)
        checks_passed = 0

        for i in range(total_checks):
            if self._is_process_alive(target_pid):
                checks_passed += 1
            if i < total_checks - 1:
                time.sleep(delay)

        alive = self._is_process_alive(target_pid)
        stable = checks_passed == total_checks and alive

        return {
            "alive": alive,
            "pid": target_pid,
            "stable": stable,
            "checks_passed": checks_passed,
            "total_checks": total_checks,
            "executable_path": self._last_launch_executable_path,
            "app_id": self._last_launch_app_id,
            "was_owned": self._last_launch_was_owned,
        }

    def verify_estabilidad_minima_proceso_ventana(
        self,
        root_pid: Optional[int] = None,
        window: Any = None,
        application_name: str = "",
        app_id: str = "",
        estabilidad_interval: float = 2.0,
        estabilidad_checks: int = 3,
        poll_interval: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Verifica la estabilidad minima del proceso y (si se proporciona) de la
        ventana durante un intervalo definido, para evitar declarar exito a un
        proceso que se cierra inmediatamente o a una ventana que desaparece.

        Realiza comprobaciones espaciadas a lo largo del intervalo: el proceso
        debe seguir vivo y, cuando se entrega una ventana, esta debe seguir
        siendo valida, visible y pertenecer al proceso. Solo consulta estado
        real de lectura: no forza foco, maximizar, mover ni cerrar nada.

        Args:
            root_pid: PID del proceso raiz. Si es None, usa el del ultimo
                lanzamiento (_last_launch_root_pid).
            window: Objeto de ventana (pygetwindow) a verificar (opcional).
            application_name: Nombre de la aplicacion (referencia).
            app_id: Identificador de aplicacion UWP/tienda (referencia).
            estabilidad_interval: Intervalo total en segundos para las
                comprobaciones.
            estabilidad_checks: Numero de comprobaciones dentro del intervalo.
            poll_interval: Pausa entre comprobaciones. Si es None, se deriva
                del intervalo y del numero de comprobaciones.

        Returns:
            Dict con claves: status, estable, pid, root_pid, process_alive,
            window_valida, window_visible, ventana_pertenece_proceso,
            checks_passed, total_checks, estabilidad_interval,
            elapsed_seconds, executable_path, app_id, was_owned, reason,
            error.

        Estados en "status":
        - ESTABLE: proceso vivo durante todo el intervalo y, si se entrego
          una ventana, ventana valida y visible perteneciente al proceso.
        - PROCESO_CERRADO: el proceso dejo de estar vivo durante el intervalo.
        - VENTANA_CERRADA: la ventana dejo de ser una ventana valida.
        - VENTANA_NO_VISIBLE: la ventana dejo de ser visible.
        - VENTANA_NO_PERTENECE: la ventana dejo de pertenecer al proceso.
        - ERROR: no hay PID para verificar.
        """
        resultado = {
            "status": None,
            "estable": False,
            "pid": None,
            "root_pid": None,
            "process_alive": False,
            "window_valida": False,
            "window_visible": False,
            "ventana_pertenece_proceso": False,
            "checks_passed": 0,
            "total_checks": 0,
            "estabilidad_interval": 0.0,
            "elapsed_seconds": 0.0,
            "executable_path": self._last_launch_executable_path,
            "app_id": self._last_launch_app_id,
            "was_owned": self._last_launch_was_owned,
            "reason": "",
            "error": None,
        }

        target_pid = (
            int(root_pid) if root_pid is not None else self._last_launch_root_pid
        )
        if not target_pid:
            resultado.update(
                status="ERROR",
                error="No hay PID para verificar",
                reason="no se pidio ni se obtuvo un PID de proceso",
            )
            self._last_launch_state = LaunchState.FALLO
            return resultado

        target_pid = int(target_pid)
        resultado["pid"] = target_pid
        resultado["root_pid"] = target_pid

        intervalo = max(0.1, float(estabilidad_interval))
        total_checks = max(1, int(estabilidad_checks))
        if poll_interval is None:
            pausa = max(0.1, intervalo / total_checks)
        else:
            pausa = max(0.05, float(poll_interval))
        resultado["estabilidad_interval"] = intervalo

        process_pids = self._get_process_tree(target_pid)
        if not process_pids:
            process_pids = {target_pid}

        hwnd = None
        if window is not None:
            hwnd = self._get_window_handle(window)
            resultado["window_valida"] = bool(
                hwnd and self._win32_is_window(hwnd)
            )
            if resultado["window_valida"]:
                resultado["window_visible"] = bool(self._win32_is_visible(hwnd))
                win_pid = self._get_window_process_id(window)
                resultado["ventana_pertenece_proceso"] = bool(
                    win_pid is not None and win_pid in process_pids
                )

        inicio = time.monotonic()
        deadline = inicio + intervalo
        checks_passed = 0
        estado_fallo = None

        for i in range(total_checks):
            # El proceso debe seguir vivo en cada comprobacion.
            if not self._is_process_alive(target_pid):
                estado_fallo = "PROCESO_CERRADO"
                break

            # La ventana (si se entrego) debe seguir valida, visible y del proceso.
            if window is not None and hwnd:
                try:
                    if not self._win32_is_window(hwnd):
                        estado_fallo = "VENTANA_CERRADA"
                        break
                    if not self._win32_is_visible(hwnd):
                        estado_fallo = "VENTANA_NO_VISIBLE"
                        break
                    win_pid = self._get_window_process_id(window)
                    if not (win_pid is not None and win_pid in process_pids):
                        estado_fallo = "VENTANA_NO_PERTENECE"
                        break
                except Exception:
                    estado_fallo = "VENTANA_NO_PERTENECE"
                    break

            checks_passed += 1
            if i < total_checks - 1:
                time.sleep(pausa)

        transcurrido = time.monotonic() - inicio
        resultado["elapsed_seconds"] = transcurrido
        resultado["total_checks"] = total_checks
        resultado["checks_passed"] = checks_passed
        resultado["process_alive"] = self._is_process_alive(target_pid)

        if estado_fallo is not None:
            resultado["status"] = estado_fallo
            resultado["reason"] = {
                "PROCESO_CERRADO": "el proceso dejo de estar vivo durante el intervalo",
                "VENTANA_CERRADA": "la ventana dejo de ser una ventana valida",
                "VENTANA_NO_VISIBLE": "la ventana dejo de ser visible",
                "VENTANA_NO_PERTENECE": "la ventana dejo de pertenecer al proceso",
            }.get(estado_fallo, "fallo de estabilidad no especificado")
            resultado["estable"] = False
            self._last_launch_state = LaunchState.FALLO
        elif checks_passed == total_checks:
            resultado["status"] = "ESTABLE"
            resultado["estable"] = True
            if window is not None:
                resultado["reason"] = "proceso y ventana estables durante el intervalo"
            else:
                resultado["reason"] = "proceso estable durante el intervalo"
            self._last_launch_state = LaunchState.ABIERTA_VERIFICADA
        else:
            resultado["status"] = "PROCESO_CERRADO"
            resultado["reason"] = "comprobaciones incompletas antes de finalizar el intervalo"
            resultado["estable"] = False
            self._last_launch_state = LaunchState.FALLO

        return resultado

    def get_launch_evidence(self) -> Dict[str, Any]:
        """Devuelve la evidencia minima del ultimo lanzamiento para correlacion.

        Incluye PID raiz, PIDs/HWNDs propios, ruta ejecutable, app_id y si el
        lanzamiento creo ventana/proceso nuevos. No registra contenido privado
        ni argumentos que puedan contener secretos.
        """
        return {
            "root_pid": self._last_launch_root_pid,
            "owned_pids": set(self._last_launch_owned_pids),
            "owned_hwnds": set(self._last_launch_owned_hwnds),
            "was_owned": self._last_launch_was_owned,
            "executable_path": self._last_launch_executable_path,
            "app_id": self._last_launch_app_id,
            "launch_state": self._last_launch_state.value if self._last_launch_state else None,
            "tipo_destino": self._last_launch_tipo_destino,
            "fuente": self._last_launch_fuente,
            "destino_validado": self._last_launch_destino_validado,
            "timestamps": dict(self._last_launch_timestamps),
            "ventana": dict(self._last_launch_window_info),
        }

    @staticmethod
    def _clasificar_tipo_destino_por_ruta(ruta: str) -> str:
        """Clasifica el tipo de destino a partir de su ruta, sin abrir nada."""
        if not ruta or not isinstance(ruta, str):
            return "desconocido"
        if ruta.casefold().endswith(".lnk"):
            return "acceso_directo"
        if ruta.casefold().endswith(".exe"):
            return "ejecutable"
        return "desconocido"

    def registrar_ventana_lanzamiento(
        self,
        hwnd: Optional[int],
        visible: Optional[bool] = None,
        monitor_id: Optional[str] = None,
        en_segunda_pantalla: Optional[bool] = None,
    ) -> None:
        """Registra la informacion de ventana del ultimo lanzamiento para la evidencia.

        Solo almacena identificadores de ventana y monitor (no coordenadas,
        titulos ni contenido privado).
        """
        self._last_launch_window_info = {
            "hwnd": hwnd,
            "visible": visible,
            "monitor_id": monitor_id,
            "en_segunda_pantalla": en_segunda_pantalla,
        }
        if hwnd is not None:
            self._last_launch_timestamps["ventana_detectada"] = time.time()

    def guardar_evidencia_lanzamiento(self, ruta_archivo: Optional[str] = None) -> Optional[str]:
        """Guarda la evidencia tecnica minima del ultimo lanzamiento en JSON.

        Incluye tipo de destino, fuente, ruta/identificador validado, PID o
        identificador equivalente, ventana y tiempos. No registra contenido
        privado ni argumentos que puedan contener secretos. La escritura es
        atomica (archivo temporal + reemplazo).

        Retorna la ruta del archivo escrito, o None si no hubo lanzamiento
        previo o no se pudo escribir.
        """
        if self._last_launch_state is None and self._last_launch_root_pid is None:
            return None
        evidencia = self.get_launch_evidence()
        timestamps = dict(evidencia.get("timestamps", {}))
        timestamps["fin"] = time.time()
        if timestamps.get("inicio") is not None:
            try:
                timestamps["duracion_segundos"] = round(
                    float(timestamps["fin"]) - float(timestamps["inicio"]), 4
                )
            except (TypeError, ValueError):
                pass
        serializable = {
            "root_pid": evidencia.get("root_pid"),
            "owned_pids": sorted(int(p) for p in evidencia.get("owned_pids", set())),
            "owned_hwnds": sorted(int(h) for h in evidencia.get("owned_hwnds", set())),
            "was_owned": bool(evidencia.get("was_owned", False)),
            "executable_path": evidencia.get("executable_path"),
            "app_id": evidencia.get("app_id"),
            "launch_state": evidencia.get("launch_state"),
            "tipo_destino": evidencia.get("tipo_destino"),
            "fuente": evidencia.get("fuente", ""),
            "destino_validado": evidencia.get("destino_validado"),
            "timestamps": timestamps,
            "ventana": evidencia.get("ventana", {}),
            "guardado_en": time.time(),
        }
        if ruta_archivo is None:
            raiz_proyecto = Path(__file__).resolve().parents[3]
            ruta_archivo = str(raiz_proyecto / "data" / "launch_evidence.json")
        ruta = Path(ruta_archivo)
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = ruta.with_suffix(ruta.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            os.replace(tmp, ruta)
            self._last_launch_evidence_path = str(ruta)
            return str(ruta)
        except Exception:
            return None

    def _wait_for_application_window(self, application_name: str, app_id: str, before_hwnds: Set[int], before_pids: Optional[Set[int]] = None, timeout: float = 12.0) -> Any:
        before_pids = before_pids or set()
        deadline = time.monotonic() + max(0.0, float(timeout))
        best = None
        best_score = -1
        while time.monotonic() < deadline:
            candidates = []
            allow_console = (
                self._get_application_type(application_name)
                == ApplicationType.CMD
            )
            for window in self._get_windows():
                if not self._window_is_usable(window, allow_console=allow_console):
                    continue
                hwnd = self._get_window_handle(window)
                pid = self._get_window_process_id(window)
                if hwnd is None:
                    continue
                is_new_window = hwnd not in before_hwnds
                is_new_process = pid is not None and pid not in before_pids
                if not (is_new_window or is_new_process):
                    continue
                score = self._score_window_for_application(window, application_name, app_id)
                if score < 0:
                    continue
                if is_new_window:
                    score += 30
                if is_new_process:
                    score += 20
                candidates.append((score, window))
            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                if candidates[0][0] > best_score:
                    best_score, best = candidates[0]
                if candidates[0][0] >= 50 or len(candidates) == 1:
                    return candidates[0][1]
            time.sleep(0.4)
        return best

    def _set_window_position(self, hwnd: int, x: int, y: int) -> bool:
        try:
            USER32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
            time.sleep(0.2)
            return bool(USER32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOP), int(x), int(y), 0, 0,
                                             SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW))
        except Exception:
            return False

    def _maximize_window(self, hwnd: int) -> bool:
        try:
            return bool(USER32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE))
        except Exception:
            return False

    def _window_center(self, hwnd: int) -> Optional[Tuple[int, int]]:
        geometry = self._get_window_geometry(hwnd)
        if geometry is None:
            return None
        left, top, width, height = geometry
        return int(left + width / 2), int(top + height / 2)

    def _window_is_on_monitor(self, hwnd: int, monitor: Any) -> bool:
        center = self._window_center(hwnd)
        return bool(center and monitor.contains_point(center[0], center[1]))

    @staticmethod
    def _is_browser_application(application_name: str) -> bool:
        normalized = CalibrationManager._normalize_application_name(application_name)
        return normalized in {"chrome", "edge", "firefox", "google_chrome", "microsoft_edge", "mozilla_firefox"}

    def _open_temporary_browser_tab(self, window: Any, application_name: str) -> bool:
        """Abre una pestana temporal en una ventana de navegador existente."""
        if not self._is_browser_application(application_name):
            return True
        hwnd = self._get_window_handle(window)
        if not hwnd or not self._win32_is_window(hwnd):
            return False
        try:
            USER32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
            time.sleep(0.2)
            USER32.SetForegroundWindow(wintypes.HWND(hwnd))
            time.sleep(0.3)
            import pyautogui
            pyautogui.hotkey("ctrl", "t")
            time.sleep(0.8)
            self._temporary_browser_tab_open = True
            self._temporary_browser_hwnd = hwnd
            logger.info(r"[CALIBRATION-MANAGER] Pestana temporal abierta en %s | HWND=%s", application_name, hwnd)
            return True
        except Exception as exc:
            logger.debug("CalibrationManager._open_temporary_browser_tab: %s", exc)
            return False

    def _close_temporary_browser_tab(self) -> None:
        """Cierra unicamente la pestana temporal creada por JARVIS."""
        if not self._temporary_browser_tab_open:
            return
        hwnd = self._temporary_browser_hwnd
        try:
            if hwnd and self._win32_is_window(hwnd):
                USER32.SetForegroundWindow(wintypes.HWND(hwnd))
                time.sleep(0.2)
                import pyautogui
                pyautogui.hotkey("ctrl", "w")
                time.sleep(0.6)
                logger.info(r"[CALIBRATION-MANAGER] Pestana temporal cerrada | HWND=%s", hwnd)
        except Exception as exc:
            logger.debug("CalibrationManager._close_temporary_browser_tab: %s", exc)
        finally:
            self._temporary_browser_tab_open = False
            self._temporary_browser_hwnd = None

    def move_window_to_monitor(
        self,
        window: Any,
        monitor_number: int,
        application_name: Optional[str] = None,
    ) -> bool:
        """Mueve temporalmente cualquier ventana calibrable al monitor indicado."""
        monitor = get_monitor_info(monitor_number)
        if monitor is None or window is None:
            return False
        hwnd = self._get_window_handle(window)
        identity = application_name or (
            self._win32_get_window_title(hwnd) if hwnd else ""
        )
        allow_console = (
            self._get_application_type(identity) == ApplicationType.CMD
        )
        if not hwnd or not self._win32_is_gui_window(hwnd, allow_console=allow_console):
            return False
        if self._is_process_elevated(self._get_window_process_id(window)):
            return False
        try:
            if not self._set_window_position(hwnd, int(monitor.left), int(monitor.top)):
                return False
            time.sleep(0.5)
            if not self._window_is_on_monitor(hwnd, monitor):
                return False
            self._maximize_window(hwnd)
            time.sleep(0.8)
            return self._window_is_on_monitor(hwnd, monitor)
        except Exception:
            return False

    # ========================================================================
    # CIERRE SEGURO
    # ========================================================================

    @staticmethod
    def _post_close_message(hwnd: int) -> bool:
        try:
            return bool(USER32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0))
        except Exception:
            return False

    @staticmethod
    def _post_system_close(hwnd: int) -> bool:
        try:
            return bool(USER32.PostMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_CLOSE, 0))
        except Exception:
            return False

    def close_application_window(self, window: Any, owned_hwnds: Optional[Set[int]] = None) -> bool:
        hwnd = self._get_window_handle(window)
        if not hwnd:
            return False
        if owned_hwnds is not None and hwnd not in owned_hwnds:
            return False
        self._post_close_message(hwnd)
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            if not self._win32_is_window(hwnd):
                return True
            time.sleep(0.1)
        if self._win32_is_window(hwnd):
            self._post_system_close(hwnd)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if not self._win32_is_window(hwnd):
                return True
            time.sleep(0.1)
        return not self._win32_is_window(hwnd)

    def _get_visible_windows_for_pids(self, pids: Set[int]) -> List[Any]:
        result = []
        for window in self._get_windows():
            hwnd = self._get_window_handle(window)
            if not hwnd or self._get_window_process_id(window) not in pids:
                continue
            if self._win32_is_window(hwnd) and self._win32_is_visible(hwnd):
                result.append(window)
        return result

    def detect_window_for_process(
        self,
        root_pid: Optional[int],
        application_name: str = "",
        app_id: str = "",
        timeout: float = 10.0,
    ) -> Any:
        """
        Detecta una ventana perteneciente al proceso/aplicacion objetivo
        mediante identificadores (PID, arbol de procesos, nombre de proceso,
        app_id) y propietario (relacion HWND owner), sin aceptar una
        coincidencia basada solo en el titulo de la ventana.

        Args:
            root_pid: PID del proceso raiz (obligatorio).
            application_name: Nombre de la aplicacion (referencia; no es
                criterio suficiente por si solo).
            app_id: Identificador de aplicacion UWP/tienda (referencia).
            timeout: Tiempo maximo de espera en segundos.

        Returns:
            Objeto de ventana (pygetwindow) si se detecta una ventana
            perteneciente al proceso, o None si no se encuentra.
        """
        if not root_pid:
            return None

        process_pids = self._get_process_tree(int(root_pid))
        if not process_pids:
            process_pids = {int(root_pid)}

        deadline = time.monotonic() + max(0.0, float(timeout))
        best = None
        best_score = -1

        while time.monotonic() < deadline:
            candidates = []
            for window in self._get_windows():
                if not self._window_is_usable(window, allow_console=False):
                    continue

                hwnd = self._get_window_handle(window)
                if not hwnd:
                    continue

                win_pid = self._get_window_process_id(window)

                # Criterio 1: el PID de la ventana esta en el arbol de
                # procesos del objetivo.
                pid_match = win_pid is not None and win_pid in process_pids

                # Criterio 2: el propietario (owner HWND) de la ventana
                # pertenece a una ventana cuyo PID esta en el arbol de
                # procesos del objetivo.
                owner_match = False
                if not pid_match:
                    owner_hwnd = self._win32_get_owner(hwnd)
                    if owner_hwnd:
                        owner_window = self._get_window_by_handle(owner_hwnd)
                        if owner_window is not None:
                            owner_pid = self._get_window_process_id(
                                owner_window
                            )
                            owner_match = (
                                owner_pid is not None
                                and owner_pid in process_pids
                            )

                # Rechazar coincidencia basada solo en el titulo: sin
                # identificador de proceso ni relacion de propietario,
                # la ventana no es candidata.
                if not (pid_match or owner_match):
                    continue

                score = 300 if pid_match else 150

                # Desempate por nombre de proceso y app_id (referencia,
                # nunca criterio de aceptacion por si solos).
                if application_name:
                    process_name = (
                        self._get_window_process_name(window).casefold()
                    )
                    normalized_app = self._normalize_application_name(
                        application_name
                    )
                    if normalized_app and normalized_app in process_name:
                        score += 50
                if app_id:
                    process_name = (
                        self._get_window_process_name(window).casefold()
                    )
                    normalized_id = self._normalize_application_name(app_id)
                    if normalized_id and normalized_id in process_name:
                        score += 30

                candidates.append((score, window))

            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                if candidates[0][0] > best_score:
                    best_score, best = candidates[0]
                if best_score >= 300:
                    return best

            time.sleep(0.4)

        return best

    MAX_WAIT_TIMEOUT = 30.0
    """Tiempo maximo permitido (segundos) para esperar una ventana. El timeout
    solicitado se acota a este valor para no bloquear el flujo indefinidamente."""

    INICIO_LENTO_FRACCION = 0.5
    """Fraccion del timeout a partir de la cual se considera que la deteccion
    de la ventana fue tardia (inicio lento)."""

    def wait_for_application_window(
        self,
        root_pid: Optional[int],
        application_name: str = "",
        app_id: str = "",
        timeout: float = 10.0,
        poll_interval: float = 0.4,
    ) -> Dict[str, Any]:
        """
        Espera la ventana de una aplicacion durante un timeout acotado y
        configurable, distinguiendo entre inicio lento, aplicacion de fondo,
        proceso sin interfaz y fallo de apertura.

        El timeout solicitado se acota a MAX_WAIT_TIMEOUT para evitar esperas
        indefinidas. Devuelve un diccionario con el estado observado, la
        ventana detectada (si procede), el PID, el tiempo transcurrido y
        indicadores de inicio lento y aplicacion en fondo.

        Estados devueltos en "status":
        - VENTANA_DETECTADA: ventana usable (visible) del proceso detectada
          dentro del timeout. inicio_lento=True si aparecio despues de la
          mitad del timeout.
        - APLICACION_EN_FONDO: el proceso sigue vivo y tiene una ventana, pero
          no es visible (segundo plano).
        - PROCESO_SIN_INTERFAZ: el proceso sigue vivo pero no creo ninguna
          ventana dentro del timeout.
        - FALLO_APERTURA: el proceso no esta vivo al iniciar o durante la
          espera, o el root_pid es invalido/ausente.
        """
        resultado = {
            "status": None,
            "window": None,
            "hwnd": None,
            "pid": None,
            "process_alive": False,
            "elapsed_seconds": 0.0,
            "timeout": 0.0,
            "inicio_lento": False,
            "es_fondo": False,
            "reason": "",
        }

        timeout_acotado = max(0.0, min(float(timeout), self.MAX_WAIT_TIMEOUT))
        poll_interval = max(0.1, float(poll_interval))
        resultado["timeout"] = timeout_acotado

        inicio = time.monotonic()
        deadline = inicio + timeout_acotado

        # Validar que exista un PID de proceso a esperar.
        if not root_pid:
            resultado.update(
                status="FALLO_APERTURA",
                process_alive=False,
                elapsed_seconds=0.0,
                reason="root_pid invalido o ausente: no hay proceso que esperar",
            )
            self._last_launch_state = LaunchState.FALLO
            return resultado

        root_pid = int(root_pid)

        # El proceso nunca arranco o ya murio antes de comenzar la espera.
        if not self._is_process_alive(root_pid):
            resultado.update(
                status="FALLO_APERTURA",
                process_alive=False,
                elapsed_seconds=time.monotonic() - inicio,
                reason="el proceso no esta vivo al iniciar la espera",
            )
            self._last_launch_state = LaunchState.FALLO
            return resultado

        process_pids = self._get_process_tree(root_pid)
        if not process_pids:
            process_pids = {root_pid}

        fondo_visto = False

        while time.monotonic() < deadline:
            # Si el proceso finalizo durante la espera, es fallo de apertura.
            if not self._is_process_alive(root_pid):
                resultado.update(
                    status="FALLO_APERTURA",
                    process_alive=False,
                    elapsed_seconds=time.monotonic() - inicio,
                    reason="el proceso finalizo durante la espera",
                )
                self._last_launch_state = LaunchState.FALLO
                return resultado

            restante = deadline - time.monotonic()
            sub_timeout = max(0.05, min(poll_interval, restante))

            # Buscar una ventana usable (visible) perteneciente al proceso.
            ventana = self.detect_window_for_process(
                root_pid, application_name, app_id, timeout=sub_timeout
            )
            if ventana is not None:
                hwnd = self._get_window_handle(ventana)
                visible = bool(hwnd and self._win32_is_visible(hwnd))
                pid = self._get_window_process_id(ventana) if hwnd else None
                transcurrido = time.monotonic() - inicio
                inicio_lento = (
                    timeout_acotado > 0
                    and transcurrido > timeout_acotado * self.INICIO_LENTO_FRACCION
                )
                resultado.update(
                    status="VENTANA_DETECTADA",
                    window=ventana,
                    hwnd=hwnd,
                    pid=pid,
                    process_alive=True,
                    elapsed_seconds=transcurrido,
                    inicio_lento=inicio_lento,
                    es_fondo=False,
                    reason="ventana usable del proceso detectada dentro del timeout"
                    + (" (inicio lento)" if inicio_lento else ""),
                )
                self._last_launch_state = LaunchState.VENTANA_DETECTADA
                return resultado

            # Detectar si el proceso tiene una ventana aunque no sea usable
            # (aplicacion en segundo plano) para distinguirla de sin interfaz.
            if not fondo_visto:
                for w in self._get_windows():
                    hwnd_c = self._get_window_handle(w)
                    if not hwnd_c:
                        continue
                    win_pid = self._get_window_process_id(w)
                    if win_pid is not None and win_pid in process_pids:
                        if not self._win32_is_visible(hwnd_c):
                            fondo_visto = True
                        break

            time.sleep(poll_interval)

        # Timeout alcanzado sin ventana usable.
        transcurrido = time.monotonic() - inicio
        proceso_vivo = self._is_process_alive(root_pid)
        resultado["process_alive"] = proceso_vivo
        resultado["elapsed_seconds"] = transcurrido

        if not proceso_vivo:
            resultado.update(
                status="FALLO_APERTURA",
                reason="el proceso no esta vivo al finalizar el timeout",
            )
            self._last_launch_state = LaunchState.FALLO
        elif fondo_visto:
            resultado.update(
                status="APLICACION_EN_FONDO",
                es_fondo=True,
                reason="el proceso sigue vivo pero su ventana no es visible (aplicacion en fondo)",
            )
            self._last_launch_state = LaunchState.ABIERTA_SIN_VENTANA
        else:
            resultado.update(
                status="PROCESO_SIN_INTERFAZ",
                reason="el proceso sigue vivo pero no creo ninguna ventana dentro del timeout",
            )
            self._last_launch_state = LaunchState.TIMEOUT

        return resultado

    def verify_visible_window_for_application(
        self,
        window: Any,
        application_name: str = "",
        app_id: str = "",
        root_pid: Optional[int] = None,
        owned_pids: Optional[Set[int]] = None,
    ) -> Dict[str, Any]:
        """
        Verifica que una ventana detectada sea visible y corresponda a la
        aplicacion solicitada, sin forzar foco, maximizar ni moverla.

        Solo consulta el estado real de la ventana (visibilidad, PID, nombre
        de proceso, monitor). No llama a ShowWindow, SetForegroundWindow,
        SetWindowPos ni move_window_to_monitor. Una coincidencia basada solo
        en el titulo no es suficiente para aceptar la ventana.

        Args:
            window: Objeto de ventana (pygetwindow) a verificar.
            application_name: Nombre de la aplicacion solicitada (referencia).
            app_id: Identificador de aplicacion UWP/tienda (referencia).
            root_pid: PID del proceso raiz lanzado (referencia fuerte).
            owned_pids: Conjunto de PIDs propios del lanzamiento actual.

        Returns:
            Dict con claves: verificada, visible, corresponde_aplicacion,
            ventana, hwnd, pid, process_name, window_title,
            application_name, app_id, root_pid, criterio_pid,
            criterio_nombre_proceso, criterio_titulo,
            es_visual_studio_code, monitor_id, monitor_primario,
            en_segunda_pantalla, reason.
        """
        resultado = {
            "verificada": False,
            "visible": False,
            "corresponde_aplicacion": False,
            "ventana": None,
            "hwnd": None,
            "pid": None,
            "process_name": "",
            "window_title": "",
            "application_name": application_name,
            "app_id": app_id,
            "root_pid": root_pid,
            "criterio_pid": False,
            "criterio_nombre_proceso": False,
            "criterio_titulo": False,
            "es_visual_studio_code": False,
            "monitor_id": None,
            "monitor_primario": False,
            "en_segunda_pantalla": False,
            "reason": "ventana no evaluada",
        }

        if window is None:
            resultado["reason"] = "ventana ausente: no hay objeto que verificar"
            self._last_launch_state = LaunchState.FALLO
            return resultado

        hwnd = self._get_window_handle(window)
        if not hwnd:
            resultado["reason"] = "no se obtuvo HWND de la ventana"
            self._last_launch_state = LaunchState.FALLO
            return resultado

        resultado["hwnd"] = int(hwnd)
        resultado["ventana"] = window

        if not self._win32_is_window(hwnd):
            resultado["reason"] = "el HWND ya no es una ventana valida"
            self._last_launch_state = LaunchState.FALLO
            return resultado

        # Visibilidad real: IsWindowVisible y estilo WS_VISIBLE.
        visible = bool(self._win32_is_visible(hwnd))
        try:
            style = int(self._win32_get_style(hwnd)) & 0xFFFFFFFF
            visible = visible and bool(style & WS_VISIBLE)
        except Exception:
            pass
        resultado["visible"] = visible

        # Identificacion del proceso y titulo de la ventana (solo lectura).
        pid = self._get_window_process_id(window)
        resultado["pid"] = pid
        if pid is not None:
            try:
                resultado["root_pid"] = int(root_pid) if root_pid is not None else None
            except (TypeError, ValueError):
                resultado["root_pid"] = None
        process_name = str(self._get_window_process_name(window) or "")
        resultado["process_name"] = process_name
        window_title = str(self._win32_get_window_title(hwnd) or "")
        resultado["window_title"] = window_title

        # Deteccion de Visual Studio Code a nivel de ventana (proceso o titulo).
        # Nunca se confunde con la aplicacion solicitada salvo que sea la propia.
        es_vscode_proceso = process_name.casefold() in {
            x.casefold() for x in self.VSCODE_EXECUTABLES
        }
        titulo_normalizado = self._normalize_application_name(window_title)
        es_vscode_titulo = any(
            self._normalize_application_name(x) in titulo_normalizado
            for x in self.VSCODE_NAME_PARTS
        ) or "visualstudiocode" in titulo_normalizado
        resultado["es_visual_studio_code"] = bool(es_vscode_proceso or es_vscode_titulo)

        # Corresponde a la aplicacion: PID en arbol/owned o nombre de proceso
        # esperado. El titulo solo es evidencia de apoyo, nunca suficiente.
        expected_processes = self._expected_process_names(application_name, app_id)
        process_name_casefold = process_name.casefold()
        criterio_nombre_proceso = bool(
            expected_processes
            and process_name_casefold
            and process_name_casefold
            in {p.casefold() for p in expected_processes}
        )
        resultado["criterio_nombre_proceso"] = criterio_nombre_proceso

        pid_match = False
        if pid is not None:
            process_pids: Set[int] = set()
            if root_pid is not None:
                try:
                    process_pids = set(self._get_process_tree(int(root_pid)))
                except Exception:
                    process_pids = set()
                if not process_pids:
                    process_pids = {int(root_pid)}
            elif owned_pids is not None:
                process_pids = set(owned_pids)
            pid_match = int(pid) in process_pids
        resultado["criterio_pid"] = bool(pid_match)

        titulo_normalizado_app = self._normalize_application_name(application_name)
        criterio_titulo = bool(
            titulo_normalizado_app
            and titulo_normalizado_app in titulo_normalizado
        )
        resultado["criterio_titulo"] = criterio_titulo

        corresponde = bool(pid_match or criterio_nombre_proceso)
        # Si la ventana es de Visual Studio Code, nunca corresponde a otra app.
        if (
            resultado["es_visual_studio_code"]
            and not self._is_vscode_application(application_name, app_id)
        ):
            corresponde = False
        resultado["corresponde_aplicacion"] = bool(corresponde)

        # Monitor real de la ventana (sin moverla).
        try:
            monitor = self.screen_manager.get_monitor_for_window(window)
        except Exception:
            monitor = None
        if monitor is not None:
            try:
                resultado["monitor_id"] = int(monitor.monitor_id)
            except (TypeError, ValueError):
                resultado["monitor_id"] = None
            try:
                resultado["monitor_primario"] = bool(monitor.is_primary)
            except Exception:
                resultado["monitor_primario"] = False
            resultado["en_segunda_pantalla"] = bool(
                monitor is not None and not monitor.is_primary
            )

        # Verificacion final: visible y corresponde (lectura, sin forzar nada).
        resultado["verificada"] = bool(visible and corresponde)

        if resultado["verificada"]:
            self._last_launch_state = LaunchState.ABIERTA_VERIFICADA
        else:
            self._last_launch_state = LaunchState.FALLO

        if not visible:
            resultado["reason"] = "la ventana detectada no es visible"
        elif (
            resultado["es_visual_studio_code"]
            and not resultado["corresponde_aplicacion"]
        ):
            resultado["reason"] = "la ventana pertenece a Visual Studio Code, no a la aplicacion solicitada"
        elif not corresponde:
            resultado["reason"] = "la ventana no se identifica como la aplicacion solicitada (PID o nombre de proceso no coinciden)"
        else:
            resultado["reason"] = "ventana visible y correspondiente a la aplicacion solicitada"

        return resultado

    def _force_terminate_process(self, pid: int) -> bool:
        if pid <= 0 or pid in self._last_launch_before_pids:
            return False
        try:
            import psutil
            process = psutil.Process(pid)
            children = process.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except Exception:
                    pass
            try:
                process.terminate()
            except Exception:
                pass
            _, alive = psutil.wait_procs(children + [process], timeout=1.5)
            for remaining in alive:
                if remaining.pid not in self._last_launch_before_pids:
                    try:
                        remaining.kill()
                    except Exception:
                        pass
            return not psutil.pid_exists(pid)
        except Exception:
            return False

    def _close_all_owned_windows(self, primary_window: Any, owned_hwnds: Set[int], owned_pids: Set[int]) -> bool:
        del primary_window
        handles = {h for h in owned_hwnds if h not in self._last_launch_before_hwnds}
        handles.update(self._get_window_handle(w) for w in self._get_visible_windows_for_pids(owned_pids))
        handles = {h for h in handles if h}
        success = True
        for hwnd in list(handles):
            if hwnd in self._last_launch_before_hwnds or not self._win32_is_window(hwnd):
                continue
            window = self._get_window_by_handle(hwnd)
            if window is not None and not self.close_application_window(window, owned_hwnds=handles):
                success = False
        for pid in sorted(owned_pids, reverse=True):
            if pid in self._last_launch_before_pids or not self._is_process_alive(pid):
                continue
            if not self._force_terminate_process(pid) and self._is_process_alive(pid):
                success = False
        return success

    # ========================================================================
    # CALIBRACION
    # ========================================================================

    def is_application_calibrated(self, application: Any) -> bool:
        """True si existe un perfil local VALIDADO para este equipo (SQLite por
        ``machine_id``). Como compatibilidad de solo lectura, tambien acepta
        coordenadas heredadas de ``macros_coords.json``."""
        app_key = self._get_storage_application_key(str(application.get("name", "")) if isinstance(application, dict) else str(application))
        if not app_key:
            return False
        try:
            pipeline = self.get_calibration_pipeline()
            profile = pipeline.store.get_active_profile(app_key)
            status = getattr(getattr(profile, "status", None), "value", getattr(profile, "status", None))
            if profile is not None and str(status).upper() == "VALIDADO":
                return True
        except Exception as exc:
            logger.debug("CalibrationManager.is_application_calibrated (perfil local): %s", exc)
        try:
            path = get_macros_coords_path()
            if not path.exists():
                return False
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            calibraciones = data.get("calibraciones", {}) if isinstance(data, dict) else {}
            app_data = calibraciones.get(app_key, {}) if isinstance(calibraciones, dict) else {}
            if not isinstance(app_data, dict) or not app_data:
                return False
            for coords in app_data.values():
                if not isinstance(coords, dict):
                    continue
                for key, value in coords.items():
                    if isinstance(key, str) and re.fullmatch(r"s\d+", key.casefold()) and isinstance(value, list) and len(value) >= 2:
                        try:
                            int(value[0]); int(value[1]); return True
                        except (TypeError, ValueError):
                            pass
            return False
        except Exception as exc:
            logger.debug("CalibrationManager.is_application_calibrated: %s", exc)
            return False

    def _get_registered_calibrator(self, application_name: str) -> Any:
        return self.calibrators.get(
            self._get_storage_application_key(application_name)
        )

    @staticmethod
    def _instantiate_registered_calibrator(entry: Any) -> Any:
        return entry() if isinstance(entry, type) else entry

    @staticmethod
    def _invoke_registered_calibrator(calibrator: Any, monitor_number: int) -> Any:
        """Ejecuta una API de calibrador registrado sin acoplar el gestor a una app."""
        import inspect

        for method_name in (
            "calibrate",
            "calibrate_application",
            "calibrate_app",
            "calibrate_chrome",
        ):
            method = getattr(calibrator, method_name, None)
            if not callable(method):
                continue
            try:
                parameters = inspect.signature(method).parameters
                if "screen_number" in parameters:
                    return method(screen_number=monitor_number)
                if "monitor_num" in parameters:
                    return method(monitor_num=monitor_number)
                if "monitor_number" in parameters:
                    return method(monitor_number=monitor_number)
                if "screen" in parameters:
                    return method(screen=monitor_number)
                return method(monitor_number)
            except (TypeError, ValueError):
                continue
        raise AttributeError(
            "El calibrador registrado no expone una API compatible"
        )

    def _normalize_registered_result(
        self,
        application_name: str,
        screen_number: int,
        raw_result: Any,
    ) -> CalibrationResult:
        if isinstance(raw_result, CalibrationResult):
            return raw_result
        app_type = self._get_application_type(application_name)
        if not isinstance(raw_result, dict):
            return CalibrationResult(
                application_name,
                app_type,
                screen_number,
                False,
                0,
                error="El calibrador registrado devolvi\u00f3 un resultado inv\u00e1lido",
            )
        actual_screen = int(
            raw_result.get(
                "screen_number", raw_result.get("monitor", screen_number)
            )
            or screen_number
        )
        success = bool(raw_result.get("success", False))
        data = raw_result.get("calibration_data")
        if not isinstance(data, dict):
            elements = raw_result.get("elements")
            if isinstance(elements, list):
                data = {"elements": elements}
            else:
                app_key = self._get_storage_application_key(application_name)
                nested = raw_result.get(app_key)
                data = nested if isinstance(nested, dict) else raw_result
        count = int(
            raw_result.get(
                "elements_count", raw_result.get("total_elements", 0)
            )
            or 0
        )
        error = raw_result.get("error") or raw_result.get("error_message")
        return CalibrationResult(
            application_name,
            app_type,
            actual_screen,
            success,
            count,
            error=str(error) if error else None,
            calibration_data=data,
        )

    def _calibrate_registered_application(
        self, application_name: str, screen_number: int
    ) -> Optional[CalibrationResult]:
        entry = self._get_registered_calibrator(application_name)
        if entry is None:
            return None
        try:
            calibrator = self._instantiate_registered_calibrator(entry)
            raw_result = self._invoke_registered_calibrator(
                calibrator, screen_number
            )
            return self._normalize_registered_result(
                application_name, screen_number, raw_result
            )
        except Exception as exc:
            logger.error(r"[CALIBRATION-MANAGER] Error en calibrador registrado de %s monitor %s: %s", application_name, screen_number, exc)
            return CalibrationResult(
                application_name,
                self._get_application_type(application_name),
                screen_number,
                False,
                0,
                error=str(exc),
            )

    # ========================================================================
    # CALIBRACION (PIPELINE UNICO)
    # ========================================================================

    def get_calibration_pipeline(self) -> Any:
        """Pipeline unico de calibracion (``UICalibrationPipeline``), creado una vez.

        Reutiliza el ``UniversalVisualCalibrator`` del gestor para Qwen3-VL y
        aplica los filtros de calibracion del gestor (VS Code, juegos,
        herramientas administrativas) antes de abrir nada. ApplicationPreflight
        lo ejecuta el lanzador de produccion antes de lanzar.
        """
        if self._calibration_pipeline is None:
            from src.hands.calibration.calibration_pipeline import UICalibrationPipeline

            self._calibration_pipeline = UICalibrationPipeline(
                vision=self.visual_calibrator,
                calibration_policy_checker=self._calibration_policy_check,
            )
        return self._calibration_pipeline

    def set_calibration_pipeline(self, pipeline: Any) -> None:
        """Inyecta el pipeline (pruebas o configuraciones alternativas)."""
        self._calibration_pipeline = pipeline

    def _calibration_policy_check(self, application: Dict[str, Any]) -> CalibrationPreflightResult:
        """Filtros propios de calibracion sobre nombre/identificador (sin lanzar nada)."""
        name = str(application.get("name", "")).strip()
        app_id = str(application.get("app_id", "")).strip()
        if not name:
            return CalibrationPreflightResult(False, name, app_id, "Nombre de aplicacion vacio")
        if self._should_ignore_application(name, app_id):
            return CalibrationPreflightResult(False, name, app_id,
                                              "La aplicaci\u00f3n est\u00e1 bloqueada para calibraci\u00f3n",
                                              {"internal_filters": True})
        if self._is_game_application(name, app_id):
            return CalibrationPreflightResult(False, name, app_id,
                                              "La aplicaci\u00f3n est\u00e1 clasificada como juego", {"game": True})
        return CalibrationPreflightResult(True, name, app_id, checks={"internal_filters": True},
                                          source="calibration_policy")

    def _pipeline_application(self, application: Any) -> Optional[Dict[str, Any]]:
        """Nombre de lanzamiento y clave estable de almacenamiento de la aplicacion."""
        if isinstance(application, dict):
            name = str(application.get("name", "")).strip()
            app_id = str(application.get("app_id", "")).strip()
        else:
            name = str(application or "").strip()
            app_id = ""
        if not name:
            return None
        return {
            "name": name,
            "app_id": app_id,
            "app_key": self._get_storage_application_key(name) or name,
        }

    def calibrate_application(
        self, application: Any, screen_number: Optional[int] = None
    ) -> CalibrationResult:
        """Calibra una aplicacion mediante el pipeline unico de calibracion.

        Sin ``screen_number`` el monitor lo decide la politica de producto
        (si la aplicacion ya esta abierta se queda en su monitor). Con
        ``screen_number`` (``monitor_id`` de ScreenManager) se resuelve el
        monitor por su geometria real y la ventana se mueve alli.

        La resolucion, ApplicationPreflight, la apertura y la verificacion de
        proceso/ventana las hace el lanzador de produccion dentro del pipeline;
        este metodo no abre ni calibra por ninguna otra via. El perfil se
        persiste en SQLite por ``machine_id`` (no en ``macros_coords.json``).
        """
        return self._run_calibration_pipeline(application, screen_number, depth="surface")

    def calibrate_application_deep(
        self,
        application: Any,
        screen_number: Optional[int] = None,
        branch_ref: Any = None,
        policy: str = "product",
    ) -> CalibrationResult:
        """Calibracion en profundidad: superficie + exploracion segura de menus,
        pestanas y dialogos no destructivos ("calibra X a fondo").

        Con ``branch_ref`` (nombre o referencia logica de un elemento) solo se
        explora la rama necesaria para hacerlo visible (peticion del Planner).
        """
        depth = "branch" if branch_ref else "deep"
        return self._run_calibration_pipeline(
            application, screen_number, depth=depth, branch_ref=branch_ref, policy=policy
        )

    def _run_calibration_pipeline(
        self,
        application: Any,
        screen_number: Optional[int],
        depth: str,
        branch_ref: Any = None,
        policy: str = "product",
    ) -> CalibrationResult:
        app_info = self._pipeline_application(application)
        if app_info is None:
            return CalibrationResult(
                str(application), ApplicationType.GENERIC, int(screen_number or 0), False, 0,
                error="Aplicaci\u00f3n no encontrada",
            )
        app_name = app_info["name"]
        app_type = self._get_application_type(app_name)
        monitor_reference: Any = None
        if screen_number is not None:
            try:
                monitor_reference = int(screen_number)
            except (TypeError, ValueError):
                monitor_reference = str(screen_number)
        try:
            pipeline = self.get_calibration_pipeline()
            report = pipeline.calibrate(
                app_info,
                monitor_reference=monitor_reference,
                policy=policy,
                depth=depth,
                branch_ref=branch_ref,
            )
        except Exception as exc:
            logger.error(r"[CALIBRATION-MANAGER] Error en el pipeline de calibracion de %s: %s", app_name, exc)
            return CalibrationResult(app_name, app_type, int(screen_number or 0), False, 0, error=str(exc))
        return self._report_to_result(report, app_type, screen_number)

    def _report_to_result(
        self, report: Any, app_type: ApplicationType, screen_number: Optional[int]
    ) -> CalibrationResult:
        """Convierte ``CalibrationReport`` en ``CalibrationResult`` (compatibilidad)."""
        legacy_screen = 0
        try:
            legacy_screen = int(self.get_calibration_pipeline().legacy_screen_number(report.display or {}))
        except Exception as exc:
            logger.debug("CalibrationManager._report_to_result: %s", exc)
        if not legacy_screen and screen_number is not None:
            try:
                legacy_screen = int(screen_number)
            except (TypeError, ValueError):
                legacy_screen = 0
        elements = []
        for element in list(getattr(report, "legacy_elements", []) or []):
            item = dict(element)
            item["screen"] = legacy_screen
            elements.append(item)
        return CalibrationResult(
            report.app_name,
            app_type,
            legacy_screen,
            bool(report.success),
            len(elements),
            error=None if report.success else (report.error or "La calibraci\u00f3n no produjo resultados"),
            calibration_data={
                "elements": elements,
                "profile_id": report.profile_id,
                "report": report.to_dict(),
            },
        )

    def get_planner_resources(self, application: Any, window_id: int) -> List[Dict[str, Any]]:
        """Recursos calibrados vigentes y con accion real para la ventana actual."""
        app_info = self._pipeline_application(application)
        if app_info is None:
            return []
        return self.get_calibration_pipeline().resources_for_planner(app_info["app_key"], int(window_id))

    def calibrate_all_applications(self, applications: Optional[List[Any]] = None, force: bool = False) -> Dict[str, Any]:
        self.screen_manager.refresh_monitors()
        discovered = self.discover_applications() if applications is None else self._resolve_application_list(applications)
        monitors_count = len(getattr(self.screen_manager, "monitors", []) or [])
        report: Dict[str, Any] = {
            "success": False,
            "monitors_detected": monitors_count,
            "applications_requested": len(discovered),
            "calibrated": [], "skipped": [], "failed": [], "total_elements": 0, "results": {},
        }
        if not discovered:
            return report

        configured_max = int(getattr(self.calibration_config, "max_applications", 0) or 0)
        if configured_max > 0:
            discovered = discovered[:configured_max]
            report["applications_requested"] = len(discovered)

        for application in discovered:
            app_name = str(application.get("name", "")).strip()
            app_key = self._get_storage_application_key(app_name)
            if not app_key:
                continue
            if not force and self.is_application_calibrated(app_name):
                result = CalibrationResult(app_name, self._get_application_type(app_name), 0, True, 0,
                                           skipped=True, calibration_data={"reason": "already_calibrated"})
                report["skipped"].append(app_key)
                report["results"][app_key] = result.to_dict()
                continue
            try:
                result = self.calibrate_application(application)
            except Exception as exc:
                logger.debug("CalibrationManager.calibrate_all_applications: %s", exc)
                result = CalibrationResult(app_name, self._get_application_type(app_name), 0, False, 0, error=str(exc))
            report["results"][app_key] = result.to_dict()
            report["total_elements"] += int(result.elements_count or 0)
            if result.success:
                report["calibrated"].append(app_key)
            else:
                report["failed"].append(app_key)

        report["success"] = bool(report["calibrated"] or report["skipped"])
        return report

    # ========================================================================
    # RESULTADOS / PERSISTENCIA
    # ========================================================================

    def _extract_element_center(self, element: Dict[str, Any]) -> Optional[Tuple[int, int]]:
        for key in ("center", "absolute"):
            value = element.get(key)
            if key == "center" and isinstance(value, (list, tuple)) and len(value) >= 2:
                try:
                    return int(round(float(value[0]))), int(round(float(value[1])))
                except (TypeError, ValueError):
                    pass
            if key == "absolute" and isinstance(value, dict):
                try:
                    return int(round(float(value["x"]))), int(round(float(value["y"])))
                except (KeyError, TypeError, ValueError):
                    pass
        bbox = element.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                return int(round((float(bbox[0]) + float(bbox[2])) / 2.0)), int(round((float(bbox[1]) + float(bbox[3])) / 2.0))
            except (TypeError, ValueError):
                pass
        return None

    def _build_application_coordinates(self, application_results: List[CalibrationResult]) -> Dict[str, Dict[str, List[int]]]:
        coordinates: Dict[str, Dict[str, List[int]]] = {}
        for result in application_results:
            if not result.success or not result.calibration_data:
                continue
            elements = result.calibration_data.get("elements", [])
            if not isinstance(elements, list):
                continue
            monitor = get_monitor_info(result.screen_number)
            screen_key = f"s{int(result.screen_number)}"
            for element in elements:
                if not isinstance(element, dict):
                    continue
                name = self._normalize_element_name(element.get("name") or element.get("text"))
                center = self._extract_element_center(element)
                if not name or center is None:
                    continue
                x, y = center
                if monitor is not None and not monitor.contains_point(x, y):
                    continue
                coordinates.setdefault(name, {})[screen_key] = [int(x), int(y)]
        return coordinates

    def _save_application_calibration(self, application_name: str, calibration_results: List[CalibrationResult]) -> None:
        coordinates = self._build_application_coordinates(calibration_results)
        self._save_coordinate_map(application_name, coordinates)

    def _save_coordinate_map(self, application_name: str, coordinates: Dict[str, Dict[str, List[int]]]) -> None:
        if not coordinates:
            return
        path = get_macros_coords_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                    if not isinstance(data, dict):
                        data = {}
                except (json.JSONDecodeError, OSError):
                    data = {}
            else:
                data = {}
            macros = data.get("macros", {})
            if not isinstance(macros, dict):
                macros = {}
            calibraciones = data.get("calibraciones", {})
            if not isinstance(calibraciones, dict):
                calibraciones = {}
            app_key = self._get_storage_application_key(application_name)
            existing = calibraciones.get(app_key, {})
            if not isinstance(existing, dict):
                existing = {}
            merged: Dict[str, Dict[str, List[int]]] = {}
            for element_name, coords in existing.items():
                if not isinstance(coords, dict):
                    continue
                normalized_name = self._normalize_element_name(element_name)
                if not normalized_name:
                    continue
                copied: Dict[str, List[int]] = {}
                for screen_key, coordinate in coords.items():
                    if not isinstance(screen_key, str) or not re.fullmatch(r"s\d+", screen_key.casefold()):
                        continue
                    if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
                        continue
                    try:
                        copied[screen_key.casefold()] = [int(coordinate[0]), int(coordinate[1])]
                    except (TypeError, ValueError):
                        pass
                if copied:
                    merged[normalized_name] = copied
            for element_name, coords in coordinates.items():
                if not isinstance(coords, dict):
                    continue
                target = merged.setdefault(element_name, {})
                for screen_key, coordinate in coords.items():
                    if isinstance(screen_key, str) and re.fullmatch(r"s\d+", screen_key.casefold()) and isinstance(coordinate, (list, tuple)) and len(coordinate) >= 2:
                        try:
                            target[screen_key.casefold()] = [int(coordinate[0]), int(coordinate[1])]
                        except (TypeError, ValueError):
                            pass
            calibraciones[app_key] = merged
            data["macros"] = macros
            data["calibraciones"] = calibraciones
            temp = path.with_suffix(".json.tmp")
            with open(temp, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
            temp.replace(path)
        except Exception as exc:
            logger.debug("CalibrationManager._save_coordinate_map: %s", exc)

    # ========================================================================
    # RESOLUCION / NOMBRES
    # ========================================================================

    def _resolve_application(self, application: Any) -> Optional[Dict[str, str]]:
        if isinstance(application, dict):
            name = str(application.get("name", "")).strip()
            app_id = str(application.get("app_id", "")).strip()
            return {"name": name, "app_id": app_id} if name and app_id else None
        name = str(application).strip()
        if not name:
            return None
        normalized_target = self._normalize_application_name(name)
        discovered = self.discover_applications()
        for item in discovered:
            if self._normalize_application_name(item["name"]) == normalized_target:
                return item
        canonical = self._get_storage_application_key(name)
        for item in discovered:
            if self._get_storage_application_key(item["name"]) == canonical:
                return item
        for item in discovered:
            normalized_name = self._normalize_application_name(item["name"])
            if normalized_target and normalized_target in normalized_name:
                return item
        return None

    def _resolve_application_list(self, applications: List[Any]) -> List[Dict[str, str]]:
        resolved: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for application in applications:
            item = self._resolve_application(application)
            if item is None:
                continue
            key = item["app_id"].casefold()
            if key in seen:
                continue
            seen.add(key)
            resolved.append(item)
        return resolved

    def _get_application_type(self, application_name: str) -> ApplicationType:
        normalized = self._normalize_application_name(application_name)
        if "chrome" in normalized:
            return ApplicationType.CHROME
        if "edge" in normalized:
            return ApplicationType.EDGE
        if "firefox" in normalized:
            return ApplicationType.FIREFOX
        if "notepad" in normalized or "bloc_de_notas" in normalized:
            return ApplicationType.NOTEPAD
        if "calculator" in normalized or "calculadora" in normalized:
            return ApplicationType.CALCULATOR
        if "paint" in normalized:
            return ApplicationType.PAINT
        if "explorer" in normalized or "explorador" in normalized:
            return ApplicationType.EXPLORER
        if normalized in {"cmd", "command_prompt"} or "simbolo_del_sistema" in normalized:
            return ApplicationType.CMD
        if "spotify" in normalized:
            return ApplicationType.SPOTIFY
        return ApplicationType.GENERIC

    @classmethod
    def _get_storage_application_key(cls, application_name: str) -> str:
        normalized = cls._normalize_application_name(application_name)
        if not normalized:
            return ""
        if normalized in cls.STORAGE_NAME_ALIASES:
            return cls.STORAGE_NAME_ALIASES[normalized]
        if "chrome" in normalized:
            return "chrome"
        if "edge" in normalized:
            return "edge"
        if "firefox" in normalized:
            return "firefox"
        if "spotify" in normalized:
            return "spotify"
        if "notepad" in normalized or "bloc_de_notas" in normalized:
            return "notepad"
        if "calculator" in normalized or "calculadora" in normalized:
            return "calculator"
        if "paint" in normalized:
            return "paint"
        if "explorer" in normalized or "explorador" in normalized:
            return "explorer"
        if normalized in {"cmd", "command_prompt"} or "simbolo_del_sistema" in normalized:
            return "cmd"
        return normalized

    @staticmethod
    def _normalize_application_name(name: str) -> str:
        if not name:
            return ""
        normalized = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii").casefold()
        return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")

    @staticmethod
    def _normalize_element_name(name: Any) -> str:
        if name is None:
            return ""
        normalized = unicodedata.normalize("NFKD", str(name).strip()).encode("ascii", "ignore").decode("ascii").casefold()
        return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")

    # ========================================================================
    # UTILIDADES / LEGACY
    # ========================================================================

    def get_calibration_statistics(self) -> Dict[str, Any]:
        path = get_macros_coords_path()
        total_elements = 0
        apps: List[str] = []
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                calibraciones = data.get("calibraciones", {}) if isinstance(data, dict) else {}
                if isinstance(calibraciones, dict):
                    apps = list(calibraciones.keys())
                    total_elements = sum(len(value) for value in calibraciones.values() if isinstance(value, dict))
        except Exception:
            pass
        return {
            "total_elements": total_elements,
            "calibrated_applications": apps,
            "available_applications": len(self.discover_applications()),
            "monitors_detected": len(getattr(self.screen_manager, "monitors", []) or []),
        }

    # ========================================================================
    # REQUISITOS DE CALIBRACION (FASE 3.5) CONECTADOS AL DESCUBRIMIENTO
    # ========================================================================

    def get_aplicaciones_con_requisito_de_calibracion(
        self,
        aplicaciones: Optional[List[Dict[str, str]]] = None,
        app_manager: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Devuelve, para cada aplicacion (descubierta por defecto), su requisito
        de calibracion de la fase 3.5 separado del resultado de calibracion.

        Requisito (3.5.1.1 y 3.5.1.2): los elementos declarados en
        ApplicationKnowledge.calibration_policy del catalogo de
        ApplicationManager. Las aplicaciones descubiertas se vinculan al
        catalogo global sin modificarlo. Si no se pasa app_manager se usa el
        gestor global de aplicaciones.
        Resultado (3.5.1.3): si la aplicacion ya esta calibrada segun
        CalibrationManager.is_application_calibrated (macros_coords.json).

        Cada entrada devuelve:
        - name: nombre de la aplicacion.
        - app_id: identificador de paquete cuando lo hay.
        - requiere_calibracion: True si declara al menos un elemento a calibrar.
        - elementos_requeridos: nombres de los elementos que requieren
          calibracion (requisito de 3.5).
        - ya_calibrada: True si la aplicacion ya tiene calibracion vigente
          (resultado de 3.5).
        - estado: "calibrada" (requisito y resultado resueltos), "pendiente"
          (requiere calibracion y no esta hecha) o "sin_requisito".
        - fuente: origen de descubrimiento de la aplicacion.
        """
        if aplicaciones is None:
            aplicaciones = self.discover_applications()
        resultado: List[Dict[str, Any]] = []
        if app_manager is None:
            try:
                from src.hands.apps.applications_core import get_application_manager

                app_manager = get_application_manager()
            except Exception:
                app_manager = None
        for app in aplicaciones or []:
            if not isinstance(app, dict):
                continue
            name = str(app.get("name", "")).strip()
            app_id = str(app.get("app_id", "")).strip()
            if not name:
                continue
            elementos_requeridos: List[str] = []
            if app_manager is not None:
                try:
                    conocimiento = app_manager.get_application(name)
                    if conocimiento is not None:
                        elementos_requeridos = list(
                            getattr(conocimiento, "calibration_policy", None) or []
                        )
                except Exception:
                    elementos_requeridos = []
            ya_calibrada = bool(self.is_application_calibrated(app))
            requiere = bool(elementos_requeridos)
            if ya_calibrada:
                estado = "calibrada"
            elif requiere:
                estado = "pendiente"
            else:
                estado = "sin_requisito"
            resultado.append(
                {
                    "name": name,
                    "app_id": app_id,
                    "requiere_calibracion": requiere,
                    "elementos_requeridos": elementos_requeridos,
                    "ya_calibrada": ya_calibrada,
                    "estado": estado,
                    "fuente": str(app.get("source", "")).strip() or None,
                }
            )
        return resultado


# ============================================================================
# SINGLETON
# ============================================================================

_calibration_manager: Optional[CalibrationManager] = None


def get_calibration_manager() -> CalibrationManager:
    global _calibration_manager
    if _calibration_manager is None:
        _calibration_manager = CalibrationManager()
    return _calibration_manager
