"""
Preflight de aplicaciones para JARVIS.

Actúa como política previa a la apertura, manipulación y calibración de una
aplicación. No abre aplicaciones ni ejecuta acciones de escritorio.

Responsabilidades:
- bloquear aplicaciones conocidas como administrativas/técnicas;
- resolver, cuando sea posible, el ejecutable real;
- inspeccionar el manifest sin ejecutar el binario;
- detectar requisitos de elevación o uiAccess;
- exponer disponibilidad, estado de login y recursos conocidos cuando el
  conocimiento de la aplicación los proporcione;
- devolver una decisión estructurada para que CalibrationManager u otros
  planificadores puedan detenerse antes de capturar una interfaz incorrecta.

El módulo no debe asumir que una aplicación está autenticada solo porque
puede abrirse. Cuando una aplicación declara que necesita login y no existe
confirmación de sesión válida, el resultado queda bloqueado o indeterminado
según el nivel de información disponible.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PreflightResult:
    """Resultado estructurado del preflight."""

    allowed: bool
    reason: str
    executable_path: Optional[str] = None
    requires_elevation: bool = False
    confidence: str = "unknown"
    availability: str = "unknown"
    login_required: Optional[bool] = None
    logged_in: Optional[bool] = None
    resources_available: Optional[bool] = None
    blocked_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "executable_path": self.executable_path,
            "requires_elevation": self.requires_elevation,
            "confidence": self.confidence,
            "availability": self.availability,
            "login_required": self.login_required,
            "logged_in": self.logged_in,
            "resources_available": self.resources_available,
            "blocked_by": self.blocked_by,
        }


class ApplicationPreflight:
    """
    Analiza una aplicación antes de que CalibrationManager la abra.

    No ejecuta la aplicación y no realiza capturas.
    """

    BLOCKED_NAME_PARTS = {
        "application verifier",
        "application_verifier",
        "verifier",
        "administrator",
        "administrador",
        "admin tool",
        "herramienta administrativa",
        "task scheduler",
        "programador de tareas",
        "event viewer",
        "visor de eventos",
        "computer management",
        "administracion de equipos",
        "device manager",
        "administrador de dispositivos",
        "registry editor",
        "editor del registro",
        "local security policy",
        "directiva de seguridad local",
        "hyper v",
        "active directory",
        "windows defender firewall",
        "firewall con seguridad avanzada",
        "services",
        "servicios",
        "iscsi",
    }

    BLOCKED_APP_ID_PARTS = {
        "application_verifier",
        "verifier",
        "task_scheduler",
        "event_viewer",
        "computer_management",
        "device_manager",
        "registry",
        "hyper_v",
        "active_directory",
        "security_policy",
        "firewall",
        "services",
        "administrative",
        "elevated",
    }

    RISKY_EXECUTION_LEVELS = {
        "requireadministrator",
        "highestavailable",
    }

    DEFAULT_RESOURCE_KEYS = (
        "required_resources",
        "resources",
    )

    POWERSHELL_TIMEOUT = 10

    def __init__(self) -> None:
        self._executable_cache: Dict[str, Optional[str]] = {}
        self._manifest_cache: Dict[str, Dict[str, Any]] = {}

    # ======================================================================
    # API PÚBLICA
    # ======================================================================

    def check(
        self,
        application: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analiza una aplicación sin ejecutarla.

        La información de login y recursos puede llegar desde el conocimiento
        de la aplicación. Este módulo no inventa ese estado.
        """

        if not isinstance(application, dict):
            return self._result(
                allowed=False,
                reason="Datos de aplicación inválidos",
                confidence="high",
                blocked_by="invalid_application",
                availability="unknown",
            )

        name = str(application.get("name", "")).strip()
        app_id = str(application.get("app_id", "")).strip()

        login_required = self._optional_bool(application.get("login_required"))
        logged_in = self._optional_bool(application.get("logged_in"))
        resources_available = self._resolve_resources_status(application)

        if not name:
            return self._result(
                allowed=False,
                reason="Nombre de aplicación vacío",
                confidence="high",
                availability="unknown",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=resources_available,
                blocked_by="invalid_application",
            )

        if self._name_is_blocked(name):
            return self._result(
                allowed=False,
                reason="Aplicación administrativa/técnica no apta para calibración automática",
                confidence="high",
                availability="unknown",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=resources_available,
                blocked_by="blocked_name",
            )

        if self._app_id_is_blocked(app_id):
            return self._result(
                allowed=False,
                reason="AppID asociado a una aplicación administrativa/técnica",
                confidence="high",
                availability="unknown",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=resources_available,
                blocked_by="blocked_app_id",
            )

        if login_required is True and logged_in is False:
            return self._result(
                allowed=False,
                reason="La aplicación requiere login y no existe una sesión válida",
                confidence="high",
                availability="unknown",
                login_required=True,
                logged_in=False,
                resources_available=resources_available,
                blocked_by="login_required",
            )

        if login_required is True and logged_in is not True:
            return self._result(
                allowed=False,
                reason="La aplicación requiere login pero el estado de sesión no está confirmado",
                confidence="medium",
                availability="unknown",
                login_required=True,
                logged_in=logged_in,
                resources_available=resources_available,
                blocked_by="login_unknown",
            )

        if resources_available is False:
            return self._result(
                allowed=False,
                reason="No están disponibles todos los recursos requeridos por la aplicación",
                confidence="high",
                availability="unknown",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=False,
                blocked_by="resources_unavailable",
            )

        executable_path = self.resolve_executable(
            name=name,
            app_id=app_id,
        )

        if not executable_path:
            return self._result(
                allowed=True,
                reason=(
                    "No se pudo resolver el ejecutable; se mantiene la apertura "
                    "como permitida y la elevación deberá comprobarse también después de abrir"
                ),
                executable_path=None,
                requires_elevation=False,
                confidence="low",
                availability="unknown",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=resources_available,
            )

        manifest_info = self.inspect_executable_manifest(executable_path)

        if not manifest_info.get("found"):
            return self._result(
                allowed=True,
                reason="Manifest no disponible o sin nivel de elevación detectable",
                executable_path=executable_path,
                requires_elevation=False,
                confidence="medium",
                availability="available",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=resources_available,
            )

        requested_level = str(
            manifest_info.get("requested_execution_level", "") or ""
        ).casefold()
        ui_access = bool(manifest_info.get("ui_access", False))

        if requested_level in self.RISKY_EXECUTION_LEVELS:
            return self._result(
                allowed=False,
                reason=f"Manifest solicita requestedExecutionLevel={requested_level}",
                executable_path=executable_path,
                requires_elevation=True,
                confidence="high",
                availability="available",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=resources_available,
                blocked_by="elevation_manifest",
            )

        if ui_access:
            return self._result(
                allowed=False,
                reason="Manifest solicita uiAccess=true",
                executable_path=executable_path,
                requires_elevation=True,
                confidence="high",
                availability="available",
                login_required=login_required,
                logged_in=logged_in,
                resources_available=resources_available,
                blocked_by="ui_access",
            )

        return self._result(
            allowed=True,
            reason="No se detectaron requisitos de elevación ni bloqueos de preflight",
            executable_path=executable_path,
            requires_elevation=False,
            confidence="high",
            availability="available",
            login_required=login_required,
            logged_in=logged_in,
            resources_available=resources_available,
        )

    def check_application(
        self,
        application: Dict[str, Any],
    ) -> PreflightResult:
        """Versión tipada del chequeo principal."""

        data = self.check(application)
        return PreflightResult(**data)

    def is_safe_to_calibrate(
        self,
        application: Dict[str, Any],
    ) -> bool:
        """Indica si el resultado actual permite iniciar una calibración."""

        result = self.check(application)
        return bool(result.get("allowed", False))

    def check_login_state(
        self,
        application: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evalúa únicamente el conocimiento explícito de login disponible.

        No intenta detectar visualmente una sesión. La detección visual debe
        pertenecer a una capa de conocimiento/percepción específica de la
        aplicación.
        """

        login_required = (
            self._optional_bool(application.get("login_required"))
            if isinstance(application, dict)
            else None
        )

        logged_in = (
            self._optional_bool(application.get("logged_in"))
            if isinstance(application, dict)
            else None
        )

        if login_required is True:
            if logged_in is True:
                return {
                    "status": "authenticated",
                    "login_required": True,
                    "logged_in": True,
                    "allowed": True,
                }

            if logged_in is False:
                return {
                    "status": "not_authenticated",
                    "login_required": True,
                    "logged_in": False,
                    "allowed": False,
                }

            return {
                "status": "unknown",
                "login_required": True,
                "logged_in": None,
                "allowed": False,
            }

        if login_required is False:
            return {
                "status": "not_required",
                "login_required": False,
                "logged_in": logged_in,
                "allowed": True,
            }

        return {
            "status": "unknown",
            "login_required": None,
            "logged_in": logged_in,
            "allowed": True,
        }

    def check_resources(
        self,
        application: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evalúa recursos explícitamente conocidos por la aplicación."""

        status = self._resolve_resources_status(application)

        if status is True:
            return {
                "status": "available",
                "available": True,
            }

        if status is False:
            return {
                "status": "unavailable",
                "available": False,
            }

        return {
            "status": "unknown",
            "available": None,
        }

    # ======================================================================
    # NOMBRES
    # ======================================================================

    def _name_is_blocked(self, name: str) -> bool:
        normalized = self._normalize(name)
        if not normalized:
            return True

        return any(
            normalized_blocked in normalized
            for normalized_blocked in self._normalized_values(self.BLOCKED_NAME_PARTS)
            if normalized_blocked
        )

    def _app_id_is_blocked(self, app_id: str) -> bool:
        normalized = self._normalize(app_id)
        if not normalized:
            return False

        return any(
            normalized_blocked in normalized
            for normalized_blocked in self._normalized_values(self.BLOCKED_APP_ID_PARTS)
            if normalized_blocked
        )

    # ======================================================================
    # RECURSOS / ESTADO CONOCIDO
    # ======================================================================

    def _resolve_resources_status(
        self,
        application: Dict[str, Any],
    ) -> Optional[bool]:
        if not isinstance(application, dict):
            return None

        explicit = application.get("resources_available")
        explicit_bool = self._optional_bool(explicit)
        if explicit_bool is not None:
            return explicit_bool

        resources = None
        for key in self.DEFAULT_RESOURCE_KEYS:
            if key in application:
                resources = application.get(key)
                break

        if resources is None:
            return None

        if isinstance(resources, bool):
            return resources

        if isinstance(resources, dict):
            values = resources.values()
            statuses = [self._optional_bool(value) for value in values]
            normalized = [value for value in statuses if value is not None]
            if not normalized:
                return None
            return all(normalized)

        if isinstance(resources, (list, tuple, set)):
            if not resources:
                return True
            statuses = [self._optional_bool(value) for value in resources]
            normalized = [value for value in statuses if value is not None]
            if not normalized:
                return None
            return all(normalized)

        return self._optional_bool(resources)

    @staticmethod
    def _optional_bool(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value

        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "1", "yes", "si", "sí", "available", "ok"}:
                return True
            if normalized in {"false", "0", "no", "unavailable", "disabled"}:
                return False

        return None

    # ======================================================================
    # RESOLUCIÓN DEL EJECUTABLE
    # ======================================================================

    def resolve_executable(
        self,
        name: str,
        app_id: str,
    ) -> Optional[str]:
        cache_key = f"{name.casefold()}|{app_id.casefold()}"

        if cache_key in self._executable_cache:
            return self._executable_cache[cache_key]

        executable = self._resolve_from_apps_folder(
            name=name,
            app_id=app_id,
        )

        if executable:
            executable = os.path.abspath(executable)
            if not os.path.isfile(executable):
                executable = None

        self._executable_cache[cache_key] = executable
        return executable

    def _resolve_from_apps_folder(
        self,
        name: str,
        app_id: str,
    ) -> Optional[str]:
        script = r"""
$ErrorActionPreference = "SilentlyContinue"

$shell = New-Object -ComObject Shell.Application
$folder = $shell.Namespace("shell:AppsFolder")

if ($null -eq $folder) {
    exit 0
}

$items = $folder.Items()

foreach ($item in $items) {
    $itemName = [string]$item.Name
    $aumid = [string]$item.ExtendedProperty("System.AppUserModel.ID")
    $target = [string]$item.ExtendedProperty("System.Link.TargetParsingPath")
    $itemPath = [string]$item.Path

    $matched = $false

    if ($env:JARVIS_APP_ID) {
        if ($aumid -and ($aumid -ieq $env:JARVIS_APP_ID)) {
            $matched = $true
        }

        if ($itemPath -and ($itemPath -ieq $env:JARVIS_APP_ID)) {
            $matched = $true
        }
    }

    if (-not $matched -and $env:JARVIS_APP_NAME) {
        if ($itemName -ieq $env:JARVIS_APP_NAME) {
            $matched = $true
        }
    }

    if ($matched) {
        [pscustomobject]@{
            Name = $itemName
            AppUserModelId = $aumid
            Target = $target
            Path = $itemPath
        } | ConvertTo-Json -Compress

        exit 0
    }
}
"""

        env = os.environ.copy()
        env["JARVIS_APP_NAME"] = str(name)
        env["JARVIS_APP_ID"] = str(app_id)

        try:
            process = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.POWERSHELL_TIMEOUT,
                env=env,
            )

            if process.returncode != 0:
                return None

            output = process.stdout.strip()
            if not output:
                return None

            data = json.loads(output)
            if not isinstance(data, dict):
                return None

            target = str(data.get("Target", "") or "").strip()
            if target and self._is_executable(target):
                return target

            item_path = str(data.get("Path", "") or "").strip()
            if item_path and self._is_executable(item_path):
                return item_path

            return self._resolve_from_target_string(target)

        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None
        except Exception:
            return None

    @staticmethod
    def _resolve_from_target_string(target: str) -> Optional[str]:
        if not target:
            return None

        target = target.strip().strip('"')
        return target if ApplicationPreflight._is_executable(target) else None

    @staticmethod
    def _is_executable(path: str) -> bool:
        if not path:
            return False

        try:
            resolved = os.path.abspath(path)
            return os.path.isfile(resolved) and resolved.casefold().endswith(".exe")
        except Exception:
            return False

    # ======================================================================
    # MANIFEST
    # ======================================================================

    def inspect_executable_manifest(
        self,
        executable_path: str,
    ) -> Dict[str, Any]:
        normalized_path = os.path.abspath(executable_path)
        cache_key = normalized_path.casefold()

        cached = self._manifest_cache.get(cache_key)
        if cached is not None:
            return dict(cached)

        result = {
            "found": False,
            "requested_execution_level": None,
            "ui_access": False,
            "source": None,
        }

        sidecar_manifest = Path(normalized_path + ".manifest")
        if sidecar_manifest.exists():
            parsed = self._parse_manifest_file(sidecar_manifest)
            if parsed:
                result.update(parsed)
                result["source"] = str(sidecar_manifest)
                self._manifest_cache[cache_key] = dict(result)
                return dict(result)

        embedded_manifest = self._extract_embedded_manifest(normalized_path)
        if embedded_manifest:
            parsed = self._parse_manifest_xml(embedded_manifest)
            if parsed:
                result.update(parsed)
                result["source"] = normalized_path

        self._manifest_cache[cache_key] = dict(result)
        return dict(result)

    def _parse_manifest_file(self, path: Path) -> Dict[str, Any]:
        try:
            return self._parse_manifest_xml(path.read_bytes())
        except Exception:
            return {}

    def _parse_manifest_xml(self, raw: Any) -> Dict[str, Any]:
        if not raw:
            return {}

        try:
            if isinstance(raw, bytes):
                xml_text = None

                for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
                    try:
                        candidate = raw.decode(encoding)
                    except UnicodeDecodeError:
                        continue

                    if (
                        "<assembly" in candidate
                        or "<asmv3:requestedExecutionLevel" in candidate
                    ):
                        xml_text = candidate
                        break

                if xml_text is None:
                    xml_text = raw.decode("utf-8", errors="ignore")
            else:
                xml_text = str(raw)

            root = ET.fromstring(xml_text)

            requested_level = None
            ui_access = False

            for element in root.iter():
                local_name = element.tag.split("}")[-1].casefold()

                if local_name == "requestedexecutionlevel":
                    requested_level = element.attrib.get("level")

                    ui_value = element.attrib.get("uiAccess")
                    if ui_value is None:
                        ui_value = element.attrib.get("uiaccess")

                    if ui_value:
                        ui_access = ui_value.casefold() == "true"

            return {
                "found": True,
                "requested_execution_level": requested_level,
                "ui_access": ui_access,
            }

        except (ET.ParseError, ValueError, TypeError):
            return {}

    # ======================================================================
    # EXTRACCIÓN DE MANIFEST EMBEBIDO
    # ======================================================================

    def _extract_embedded_manifest(
        self,
        executable_path: str,
    ) -> Optional[bytes]:
        """Extrae RT_MANIFEST del PE sin ejecutar el binario."""

        try:
            import pefile
        except ImportError:
            return None

        pe = None

        try:
            pe = pefile.PE(executable_path, fast_load=False)

            if not hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
                return None

            manifest_type_id = 24

            for resource_type in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                if resource_type.id != manifest_type_id or not hasattr(
                    resource_type, "directory"
                ):
                    continue

                for resource_id in resource_type.directory.entries:
                    if not hasattr(resource_id, "directory"):
                        continue

                    for resource_lang in resource_id.directory.entries:
                        if not hasattr(resource_lang, "data"):
                            continue

                        data_entry = resource_lang.data
                        offset = int(data_entry.struct.OffsetToData)
                        size = int(data_entry.struct.Size)

                        return pe.get_data(offset, size)

        except Exception:
            return None
        finally:
            try:
                if pe is not None:
                    pe.close()
            except Exception:
                pass

        return None

    # ======================================================================
    # RESULTADO
    # ======================================================================

    @staticmethod
    def _result(
        allowed: bool,
        reason: str,
        executable_path: Optional[str] = None,
        requires_elevation: bool = False,
        confidence: str = "unknown",
        availability: str = "unknown",
        login_required: Optional[bool] = None,
        logged_in: Optional[bool] = None,
        resources_available: Optional[bool] = None,
        blocked_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        return PreflightResult(
            allowed=bool(allowed),
            reason=str(reason),
            executable_path=executable_path,
            requires_elevation=bool(requires_elevation),
            confidence=str(confidence),
            availability=str(availability),
            login_required=login_required,
            logged_in=logged_in,
            resources_available=resources_available,
            blocked_by=blocked_by,
        ).to_dict()

    # ======================================================================
    # CACHÉ / UTILIDADES
    # ======================================================================

    def clear_cache(self) -> None:
        """Limpia resultados de resolución y manifest."""

        self._executable_cache.clear()
        self._manifest_cache.clear()

    @staticmethod
    def _normalized_values(values: Iterable[str]) -> Set[str]:
        return {ApplicationPreflight._normalize(value) for value in values if value}

    @staticmethod
    def _normalize(value: str) -> str:
        if not value:
            return ""

        normalized = unicodedata.normalize("NFKD", str(value))
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = normalized.casefold()
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        return normalized.strip("_")


# ============================================================================
# SINGLETON
# ============================================================================


_application_preflight: Optional[ApplicationPreflight] = None


def get_application_preflight() -> ApplicationPreflight:
    global _application_preflight

    if _application_preflight is None:
        _application_preflight = ApplicationPreflight()

    return _application_preflight
