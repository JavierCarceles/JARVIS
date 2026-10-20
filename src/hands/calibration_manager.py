"""
Gestor universal de calibración de aplicaciones para JARVIS.

El gestor coordina descubrimiento, preflight, apertura segura, preparación de
ventanas, captura de monitor, calibración visual universal y persistencia.

No contiene calibradores visuales específicos por aplicación ni coordenadas,
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

import pygetwindow as gw

from src.utils.config import get_calibration_config, get_macros_coords_path
from src.utils.logger import get_logger
from src.utils.screen_manager import get_monitor_info, get_screen_manager

logger = get_logger(__name__)


# ============================================================================
# WIN32
# ============================================================================

USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32
ADVAPI32 = ctypes.windll.advapi32

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


# ============================================================================
# GESTOR
# ============================================================================


class CalibrationManager:
    """Coordinador universal de calibración multiaplicación y multimonitor."""

    ALLOWED_WINDOWS_GUI_NAMES = {
        "settings", "configuracion", "configuración", "explorador_de_archivos",
        "file_explorer", "calculadora", "calculator", "bloc_de_notas", "notepad",
        "paint", "microsoft_paint", "fotos", "photos", "correo", "mail", "calendario",
        "calendar", "reproductor_multimedia", "media_player", "peliculas_y_tv",
        "movies_and_tv", "recortes", "snipping_tool", "sticky_notes", "notas_rapidas",
        "one_note", "onenote", "mapa_de_caracteres", "character_map", "reloj", "clock",
        "explorer", "cmd", "command_prompt",
    }

    IGNORED_EXACT_NAMES = {
        "help", "ayuda", "documentation", "documentacion", "documentación", "more", "more...", ".lnk",
    }

    IGNORED_NAME_PARTS = (
        "uninstall", "desinstalar", "readme", "release notes", "notas de la versión",
        "notas de version", "changelog", "documentation", "documentación", "documentacion",
        "manuals", "manual", "module docs", "module documentation", "frequently asked questions",
        "faq", "website", "on the web", "support center", "support centre", "support", "soporte",
        "redistributable", "sample desktop apps", "sample uwp apps", "sample", "samples",
        "tools for desktop apps", "tools for uwp apps", "developer command prompt",
        "developer powershell", "native tools command prompt", "cross tools command prompt",
        "powershell ise", "git bash", "git cmd", "node.js command prompt", "node.js documentation",
        "node.js website", "python manuals", "python module docs", "python documentation", "sdk",
        "software development kit", "install additional tools", "installer", "installation center",
        "centro de instalación", "setup", "publisher",
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
        from src.hands.universal_visual_calibrator import UniversalVisualCalibrator
        self.visual_calibrator = UniversalVisualCalibrator()
        self.calibration_config = get_calibration_config()

        self.calibrators: Dict[str, Any] = {}
        self._register_builtin_calibrators()

        self._last_launch_before_hwnds: Set[int] = set()
        self._last_launch_before_pids: Set[int] = set()
        self._last_launch_owned_hwnds: Set[int] = set()
        self._last_launch_owned_pids: Set[int] = set()
        self._last_launch_window: Any = None
        self._last_launch_was_owned: bool = False
        self._last_launch_root_pid: Optional[int] = None
        self._temporary_browser_tab_open: bool = False
        self._temporary_browser_hwnd: Optional[int] = None

        self._application_metadata_by_name: Dict[str, List[Dict[str, str]]] = {}
        self._application_metadata_by_app_id: Dict[str, List[Dict[str, str]]] = {}
        self._application_metadata_all: List[Dict[str, str]] = []
        self._application_metadata_loaded = False
        self._preflight_checker: Optional[Callable[[Dict[str, str]], Any]] = None

        logger._print_log("info", r"[CALIBRATION-MANAGER] Gestor universal de calibración inicializado [file:calibration_manager.py, method:__init__, line:321]", "calibration_manager.py", "method", 321)

    def _register_builtin_calibrators(self) -> None:
        """Prepara el registro de extensiones específicas sin usarlas como flujo principal.

        La calibración normal, incluida Chrome, utiliza siempre el flujo
        universal de ventana -> monitor -> captura -> visión. Los calibradores
        específicos quedan disponibles únicamente para extensiones explícitas.
        """
        self.calibrators = {}
        logger._print_log("info", r"[CALIBRATION-MANAGER] Flujo universal habilitado para todas las aplicaciones; no se registra ningún calibrador específico por defecto [file:calibration_manager.py, method:_register_builtin_calibrators, line:332]", "calibration_manager.py", "method", 331)

    # ========================================================================
    # REGISTRO / CAPACIDADES
    # ========================================================================

    def register_calibrator(self, application_name: str, calibrator: Any) -> None:
        key = self._get_storage_application_key(application_name)
        if not key:
            raise ValueError("Nombre de aplicación vacío")
        if calibrator is None:
            raise ValueError("El calibrador no puede ser None")
        self.calibrators[key] = calibrator
        logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)

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
                                              None if result else "Preflight rechazó la aplicación", source=source)
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
            return CalibrationPreflightResult(False, str(application), reason="Aplicación no encontrada")
        name = application_info["name"]
        app_id = application_info.get("app_id", "")
        if self._should_ignore_application(name, app_id):
            return CalibrationPreflightResult(False, name, app_id,
                                              "La aplicación está bloqueada para calibración", {"internal_filters": True})
        if self._is_game_application(name, app_id):
            return CalibrationPreflightResult(False, name, app_id,
                                              "La aplicación está clasificada como juego", {"game": True})
        if self._preflight_checker is None:
            return CalibrationPreflightResult(True, name, app_id,
                                              checks={"internal_filters": True, "external_preflight": False})
        try:
            return self._normalize_preflight_result(self._preflight_checker(application_info), application_info,
                                                    "application_preflight")
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud: " + str(exc), "calibration_manager.py", "method", 344)
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
$roots = @((Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
           (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))
try {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -Filter '*.lnk' -File -Recurse -ErrorAction SilentlyContinue |
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
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
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
        logger._print_log("info", r"[CALIBRATION-MANAGER] Descubriendo aplicaciones instaladas... [file:calibration_manager.py, method:discover_applications, line:546]", "calibration_manager.py", "method", 546)
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
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)

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
        logger._print_log("info", f"Procesadas {len(applications)} aplicaciones GUI", "calibration_manager.py", "_get_gui_applications", 626)
        return applications

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
        # representativo. Para decidir si sigue siendo una ventana GUI válida,
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
        """Devuelve geometría utilizable incluso cuando la ventana está minimizada."""
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
                logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
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
        """Obtiene nombres de proceso esperados para una aplicación."""
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
            # Si conocemos el ejecutable real de la aplicación, no confundimos
            # ventanas de otro proceso basado únicamente en el título.
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
    # APERTURA / PREPARACIÓN
    # ========================================================================

    def _reset_launch_context(self) -> None:
        self._last_launch_before_hwnds = set()
        self._last_launch_before_pids = set()
        self._last_launch_owned_hwnds = set()
        self._last_launch_owned_pids = set()
        self._last_launch_window = None
        self._last_launch_was_owned = False
        self._last_launch_root_pid = None
        self._temporary_browser_tab_open = False
        self._temporary_browser_hwnd = None

    def launch_application(self, application: Dict[str, str]) -> Tuple[Set[int], bool]:
        """Reutiliza una ventana existente o lanza la aplicación de forma genérica."""
        app_name = str(application.get("name", "")).strip()
        app_id = str(application.get("app_id", "")).strip()
        executable = str(application.get("path", application.get("executable", ""))).strip()
        arguments = str(application.get("arguments", "")).strip()
        self._reset_launch_context()

        if (
            not app_name
            or self._should_ignore_application(app_name, app_id)
            or self._is_game_application(app_name, app_id)
        ):
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
                state = "minimizada" if USER32.IsIconic(wintypes.HWND(hwnd)) else "visible"
                logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
                return set(self._last_launch_before_hwnds), True

        before_hwnds = self._get_window_handles()
        before_pids = self._get_process_ids()
        self._last_launch_before_hwnds = set(before_hwnds)
        self._last_launch_before_pids = set(before_pids)

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
                    command = [path]
                    item_args = str(item.get("arguments", "")).strip()
                    if item_args:
                        command.extend(shlex.split(item_args, posix=False))
                    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    launched = True
                    break
                if not launched:
                    logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
                    return before_hwnds, False

            window = self._wait_for_application_window(app_name, app_id, before_hwnds, before_pids)
            if window is None:
                return before_hwnds, False

            hwnd = self._get_window_handle(window)
            pid = self._get_window_process_id(window)
            if hwnd is None:
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

            if self._is_process_elevated(pid):
                logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
                if owned_hwnds:
                    self._close_all_owned_windows(window, owned_hwnds, owned_pids)
                return before_hwnds, False

            logger._print_log("info", f"Aplicación lanzada: {app_name} | HWND={hwnd} | PID={pid} | owned={self._last_launch_was_owned}", "calibration_manager.py", "_launch_application_by_name", 1344)
            return before_hwnds, True
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
            return before_hwnds, False

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
        """Abre una pestaña temporal en una ventana de navegador existente."""
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
            logger._print_log("info", r"[CALIBRATION-MANAGER] Pestaña temporal abierta en %s | HWND=%s [file:calibration_manager.py, method:_open_temp_tab, line:1435]", "calibration_manager.py", "method", 1435)
            return True
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
            return False

    def _close_temporary_browser_tab(self) -> None:
        """Cierra únicamente la pestaña temporal creada por JARVIS."""
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
                logger._print_log("info", r"[CALIBRATION-MANAGER] Pestaña temporal cerrada | HWND=%s [file:calibration_manager.py, method:_close_temp_tab, line:1453]", "calibration_manager.py", "method", 1453)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
        finally:
            self._temporary_browser_tab_open = False
            self._temporary_browser_hwnd = None

    def _prepare_window_for_calibration(self, window: Any, application_name: str = "") -> Optional[Any]:
        """Restaura/maximiza una ventana y devuelve su monitor real.

        Es completamente independiente de la aplicación: sirve para
        navegadores, aplicaciones Win32, UWP/StartApps y herramientas GUI.
        No desplaza la ventana a otro monitor.
        """
        hwnd = self._get_window_handle(window)
        if not hwnd or not self._win32_is_window(hwnd):
            return None

        try:
            if self._is_process_elevated(self._get_window_process_id(window)):
                return None

            was_minimized = bool(USER32.IsIconic(wintypes.HWND(hwnd)))
            if was_minimized:
                logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
                USER32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
                time.sleep(0.5)

            USER32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
            time.sleep(0.8)

            try:
                USER32.SetForegroundWindow(wintypes.HWND(hwnd))
            except Exception:
                pass
            time.sleep(0.2)

            monitor = self.screen_manager.get_monitor_for_window(window)
            if monitor is None:
                # Volver a consultar el objeto de ventana por HWND si
                # pygetwindow tiene una instancia desactualizada.
                refreshed = self._get_window_by_handle(hwnd)
                if refreshed is not None:
                    window = refreshed
                    monitor = self.screen_manager.get_monitor_for_window(window)

            if monitor is None:
                logger._print_log("warning", r"[CALIBRATION-MANAGER] No se pudo determinar el monitor de HWND=%s tras preparar la ventana [file:calibration_manager.py, method:_prepare_window_for_calibration, line:1502]", "calibration_manager.py", "method", 1500)
                return None

            geometry = self._get_window_geometry(window)
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
            return monitor
        except Exception as exc:
            logger._print_log("error", r"[CALIBRATION-MANAGER] Error preparando HWND=%s para calibración: %s [file:calibration_manager.py, method:_prepare_window_for_calibration, line:1511]", "calibration_manager.py", "method", 1507)
            return None

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
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
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
    # CALIBRACIÓN
    # ========================================================================

    def is_application_calibrated(self, application: Any) -> bool:
        app_key = self._get_storage_application_key(str(application.get("name", "")) if isinstance(application, dict) else str(application))
        if not app_key:
            return False
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
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
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
                error="El calibrador registrado devolvió un resultado inválido",
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
            logger._print_log("error", r"[CALIBRATION-MANAGER] Error en calibrador registrado de %s monitor %s: %s [file:calibration_manager.py, method:_calibrate_registered_application, line:1781]", "calibration_manager.py", "method", 1777)
            return CalibrationResult(
                application_name,
                self._get_application_type(application_name),
                screen_number,
                False,
                0,
                error=str(exc),
            )

    def calibrate_application(
        self, application: Any, screen_number: Optional[int] = None
    ) -> CalibrationResult:
        """Calibra cualquier aplicación mediante un único flujo universal.

        Flujo:
            aplicación cerrada  -> abrir -> restaurar/maximizar -> detectar monitor
            aplicación minimizada -> restaurar/maximizar -> detectar monitor
            aplicación abierta -> maximizar -> detectar monitor
            monitor detectado -> captura -> UniversalVisualCalibrator

        Cuando ``screen_number`` es None, se calibra el monitor real donde la
        ventana queda después de prepararla. Cuando se especifica, la ventana
        se mueve temporalmente a ese monitor antes de capturar.
        """
        self.screen_manager.refresh_monitors()
        application_info = self._resolve_application(application)
        if not application_info:
            return CalibrationResult(
                str(application),
                ApplicationType.GENERIC,
                int(screen_number or 0),
                False,
                0,
                error="Aplicación no encontrada",
            )

        app_name = application_info["name"]
        app_type = self._get_application_type(app_name)
        preflight = self.preflight_application(application_info)
        if not preflight.allowed:
            return CalibrationResult(
                app_name, app_type, 0, False, 0,
                error=preflight.reason or "Aplicación rechazada por preflight",
            )

        # No usamos calibradores específicos como camino principal. La misma
        # lógica de preparación y captura se aplica a cualquier aplicación.
        _, launched = self.launch_application(application_info)
        if not launched or self._last_launch_window is None:
            return CalibrationResult(
                app_name, app_type, 0, False, 0,
                error="No se pudo abrir o detectar una ventana GUI",
            )

        window = self._last_launch_window
        owned_hwnds = set(self._last_launch_owned_hwnds)
        owned_pids = set(self._last_launch_owned_pids)
        hwnd = self._get_window_handle(window)
        snapshot = None if owned_hwnds else self._capture_window_state(hwnd)

        try:
            window_pid = self._get_window_process_id(window)
            if self._is_process_elevated(window_pid):
                return CalibrationResult(
                    app_name, app_type, 0, False, 0,
                    error="La aplicación requiere privilegios elevados",
                )

            actual_monitor = self._prepare_window_for_calibration(
                window, app_name
            )
            if actual_monitor is None:
                return CalibrationResult(
                    app_name, app_type, 0, False, 0,
                    error="No se pudo restaurar/maximizar la ventana ni determinar su monitor",
                )

            # Actualizar la instancia de ventana por HWND después de restaurar/maximizar.
            if hwnd:
                refreshed_window = self._get_window_by_handle(hwnd)
                if refreshed_window is not None:
                    window = refreshed_window

            # Los navegadores se calibran en una pestaña temporal dentro de la
            # misma ventana ya preparada. Las aplicaciones GUI normales se
            # calibran directamente sobre su ventana.
            if not self._last_launch_was_owned and self._is_browser_application(app_name):
                if not self._open_temporary_browser_tab(window, app_name):
                    return CalibrationResult(
                        app_name, app_type, 0, False, 0,
                        error="No se pudo abrir la pestaña temporal de calibración",
                    )

            if screen_number is None:
                target_monitors = [actual_monitor]
                logger._print_log("info", r"[CALIBRATION-MANAGER] %s se calibrará en su monitor real: %s [file:calibration_manager.py, method:calibrate_application, line:1877]", "calibration_manager.py", "method", 1873)
            else:
                requested_monitor = self.screen_manager.get_monitor(int(screen_number))
                if requested_monitor is None:
                    return CalibrationResult(
                        app_name, app_type, int(screen_number), False, 0,
                        error=f"Monitor {screen_number} no encontrado",
                    )
                target_monitors = [requested_monitor]

            successful: List[CalibrationResult] = []
            errors: List[str] = []

            for monitor in target_monitors:
                result = self._calibrate_open_window(
                    app_name, window, int(monitor.monitor_id)
                )
                if result.success:
                    self._save_application_calibration(app_name, [result])
                    successful.append(result)
                elif result.error:
                    errors.append(result.error)
                    logger._print_log("warning", r"[CALIBRATION-MANAGER] %s monitor %s falló: %s [file:calibration_manager.py, method:calibrate_application, line:1899]", "calibration_manager.py", "method", 1895)

            if not successful:
                return CalibrationResult(
                    app_name, app_type, 0, False, 0,
                    error="; ".join(dict.fromkeys(errors))
                    if errors else "La calibración no produjo resultados",
                )

            actual_screen = successful[0].screen_number
            return CalibrationResult(
                app_name, app_type, actual_screen, True,
                sum(r.elements_count for r in successful),
                calibration_data={"results": [r.to_dict() for r in successful]},
            )
        finally:
            self._close_temporary_browser_tab()
            if owned_hwnds:
                self._close_all_owned_windows(window, owned_hwnds, owned_pids)
            elif hwnd and snapshot is not None:
                if not self._restore_window_state(hwnd, snapshot):
                    logger._print_log("warning", r"[CALIBRATION-MANAGER] No se pudo restaurar el estado original de %s | HWND=%s [file:calibration_manager.py, method:calibrate_application, line:1920]", "calibration_manager.py", "method", 1916)
                else:
                    logger._print_log("info", r"[CALIBRATION-MANAGER] Estado original restaurado para %s | HWND=%s [file:calibration_manager.py, method:calibrate_application, line:1925]", "calibration_manager.py", "method", 1918)

    def _get_monitors_to_calibrate(self, screen_number: Optional[int]) -> List[Any]:
        self.screen_manager.refresh_monitors()
        monitors = list(getattr(self.screen_manager, "monitors", []) or [])
        if screen_number is None:
            return monitors
        try:
            requested = int(screen_number)
        except (TypeError, ValueError):
            return []
        monitor = self.screen_manager.get_monitor(requested)
        return [monitor] if monitor is not None else []

    def _calibrate_open_window(self, application_name: str, window: Any, screen_number: int) -> CalibrationResult:
        app_type = self._get_application_type(application_name)
        screenshot_path: Optional[str] = None
        try:
            target_monitor = self.screen_manager.get_monitor(screen_number)
            if target_monitor is None:
                return CalibrationResult(
                    application_name, app_type, screen_number, False, 0,
                    error=f"Monitor {screen_number} no encontrado"
                )

            current_monitor = self.screen_manager.get_monitor_for_window(window)
            if current_monitor is None:
                current_monitor = self._prepare_window_for_calibration(
                    window, application_name
                )

            if current_monitor is None:
                return CalibrationResult(
                    application_name, app_type, screen_number, False, 0,
                    error="No se pudo determinar el monitor actual de la ventana"
                )

            if current_monitor.monitor_id != target_monitor.monitor_id:
                if not self.move_window_to_monitor(
                    window, screen_number, application_name
                ):
                    return CalibrationResult(
                        application_name, app_type, screen_number, False, 0,
                        error=f"No se pudo preparar la ventana en el monitor {screen_number}"
                    )
            else:
                # Aunque ya esté en el monitor correcto, nos aseguramos de que
                # siga restaurada/maximizada antes de capturar.
                prepared = self._prepare_window_for_calibration(
                    window, application_name
                )
                if prepared is None or prepared.monitor_id != target_monitor.monitor_id:
                    return CalibrationResult(
                        application_name, app_type, screen_number, False, 0,
                        error=f"La ventana no quedó preparada en el monitor {screen_number}"
                    )

            time.sleep(1.0)
            screenshot_path = self.screen_manager.capture_monitor(screen_number)
            if not screenshot_path:
                return CalibrationResult(
                    application_name, app_type, screen_number, False, 0,
                    error=f"No se pudo capturar el monitor {screen_number}"
                )
            screenshot = Path(str(screenshot_path))
            if not screenshot.exists() or screenshot.stat().st_size <= 0:
                return CalibrationResult(
                    application_name, app_type, screen_number, False, 0,
                    error="La captura no existe o está vacía"
                )

            analysis = self.visual_calibrator.calibrate(
                application_name=application_name,
                monitor_number=screen_number,
                screenshot_path=str(screenshot),
            )
            if not isinstance(analysis, dict):
                return CalibrationResult(
                    application_name, app_type, screen_number, False, 0,
                    error="UniversalVisualCalibrator devolvió un formato inválido"
                )
            if analysis.get("success") is False or analysis.get("error"):
                return CalibrationResult(
                    application_name, app_type, screen_number, False, 0,
                    error=str(analysis.get("error", "Error en UniversalVisualCalibrator")),
                    calibration_data=analysis,
                )

            elements = self._extract_elements(analysis)
            if not elements:
                return CalibrationResult(
                    application_name, app_type, screen_number, False, 0,
                    error="No se detectaron elementos interactivos",
                    calibration_data=analysis,
                )

            return CalibrationResult(
                application_name, app_type, screen_number, True, len(elements),
                calibration_data={"elements": elements, "raw_analysis": analysis},
            )
        except Exception as exc:
            logger._print_log("error", r"[CALIBRATION-MANAGER] Error calibrando %s monitor %s: %s [file:calibration_manager.py, method:_calibrate_open_window, line:2023]", "calibration_manager.py", "method", 2019)
            return CalibrationResult(
                application_name, app_type, screen_number, False, 0, error=str(exc)
            )
        finally:
            if screenshot_path:
                try:
                    path = Path(str(screenshot_path))
                    if path.exists():
                        path.unlink()
                except Exception as exc:
                    logger._print_log("debug", r"[CALIBRATION-MANAGER] No se pudo eliminar captura temporal: %s [file:calibration_manager.py, method:_calibrate_open_window, line:2030]", "calibration_manager.py", "method", 2030)

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
                logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)
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

    def _extract_elements(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        elements = analysis.get("elements")
        if isinstance(elements, list):
            return [item for item in elements if isinstance(item, dict)]
        calibration_data = analysis.get("calibration_data")
        if isinstance(calibration_data, dict) and isinstance(calibration_data.get("elements"), list):
            return [item for item in calibration_data["elements"] if isinstance(item, dict)]
        return []

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
            logger._print_log("info", "Procesando solicitud", "calibration_manager.py", "method", 344)

    # ========================================================================
    # RESOLUCIÓN / NOMBRES
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


# ============================================================================
# SINGLETON
# ============================================================================

_calibration_manager: Optional[CalibrationManager] = None


def get_calibration_manager() -> CalibrationManager:
    global _calibration_manager
    if _calibration_manager is None:
        _calibration_manager = CalibrationManager()
    return _calibration_manager
