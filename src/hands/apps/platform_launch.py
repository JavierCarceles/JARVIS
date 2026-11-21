"""
Contrato multiplataforma de descubrimiento y lanzamiento de aplicaciones.

Un unico flujo para Windows y macOS (roadmap 3.8.9, integrado en 3.8.10.1):

    descubrimiento -> resolucion local (machine_id) -> ApplicationPreflight
                   -> lanzamiento -> verificacion de proceso/ventana

* ``ApplicationLaunchAdapter``: contrato por SO (``discover``, ``resolve``,
  ``preflight``, ``launch``, ``verify``, ``capabilities``). Implementaciones:
  ``src.hands.apps.launch_windows.WindowsLaunchAdapter`` y
  ``src.hands.apps.launch_macos.MacOSLaunchAdapter`` (escrito sin Mac para
  probar; ver su docstring).
* ``ApplicationLaunchService``: el UNICO flujo que abre aplicaciones. Lo usa la
  accion registrada ``open_application`` de ``applications_core`` y, a traves
  de ella, el ejecutor legado, el ``Executor``/``TaskExecutor`` del Planner y
  las tareas HTN. No existe otra ruta de lanzamiento paralela.
* ``link_platform_identity``: enlaza en el catalogo global la identidad de la
  misma aplicacion logica en cada SO (AUMID/fabricante-producto en Windows,
  bundle id en macOS) sin guardar rutas.

Garantias:

* ``ApplicationPreflight`` es puerta obligatoria antes de cualquier lanzamiento.
* Argumentos siempre estructurados (lista de argv); nunca se concatena una
  ruta o un nombre en una linea de shell.
* No se ejecutan candidatos en lote ni se abre nada por ser "probable".
* Si la aplicacion ya esta abierta se reutiliza; una apertura con exito no se
  repite (registro de idempotencia con validacion de proceso vivo).
* Reintentos acotados solo ANTES de haber lanzado un proceso; un lanzamiento
  realizado nunca se reintenta (evita dobles instancias).
* Errores estructurados (``OperationError``) y evidencia redactada: nunca se
  registran rutas privadas completas, usuario ni secretos.
* La ruta que pueda guardar el catalogo global es una observacion de otro
  momento/equipo: solo se lanza un destino resuelto en ESTE equipo
  (``machine_id``) y revalidado contra el SO.

MATRIZ DE DEPENDENCIAS POR OPERACION (auditoria del codigo existente)
=====================================================================

Operacion | Windows (codigo existente)                                  | macOS (este modulo / launch_macos)
--------- | ------------------------------------------------------------ | ----------------------------------
discover  | CalibrationManager.discover_applications: PowerShell          | Primer nivel de /Applications,
          | Get-StartApps + .lnk del Menu Inicio (WScript.Shell) +        | ~/Applications, /System/Applications
          | Get-AppxPackage + registro Uninstall (HKCU/HKLM);             | y Spotlight (mdfind
          | ApplicationDiscovery: PATH (primer nivel), App Paths          | kMDItemContentType ==
          | (winreg), proceso abierto (tasklist), inventario SQLite       | com.apple.application-bundle); sin
          | (application_candidates/file_entries, .exe/.lnk)              | escaneo de disco
resolve   | ApplicationDiscovery.resolver_aplicacion_por_nombre(_con_      | Info.plist (plistlib):
          | desambiguacion): catalogo -> SQLite por machine_id ->          | CFBundleIdentifier, CFBundleName,
          | revalidar_destino_aplicacion (isfile) + auto-registro;         | CFBundleDisplayName; identidad por
          | buscar_por_nombre_con_desambiguacion (fuentes nativas)         | bundle id, nunca por ruta
preflight | ApplicationPreflight.check: PowerShell shell:AppsFolder        | ApplicationPreflight.check_launch_
          | (resolve_executable, verify_app_id_in_apps_folder), SQLite     | target: bundle existente con
          | .exe, validate_launch_destination (.exe/.lnk/URI admitidas),   | Info.plist y bundle id coherente;
          | inspect_executable_manifest (pefile: requestedExecutionLevel,  | Gatekeeper/cuarentena (xattr
          | uiAccess)                                                       | com.apple.quarantine, spctl
          |                                                                | --assess) como motivo de bloqueo
classify  | LaunchClassifier: subsistema PE, GetFileVersionInfoW           | LaunchType.BUNDLE para .app
          | (ctypes.windll.version), .lnk via PowerShell Shell.Application |
launch    | applications_core: subprocess.Popen([exe]) / webbrowser;       | open -b <bundle_id> (lista de
          | CalibrationManager: explorer.exe shell:AppsFolder\\<AUMID>;    | argumentos) o NSWorkspace
          | aqui: os.startfile(.lnk / URI admitida)                        |
process   | tasklist /FI IMAGENAME (applications_core), psutil             | NSRunningApplication por bundle id
          |                                                                | (pyobjc) o psutil
window    | Contrato de escritorio (Win32 EnumWindows por PID)              | Contrato de escritorio
          |                                                                | (CGWindowListCopyWindowInfo por PID)
close     | taskkill /f /im (applications_core); aqui: WM_CLOSE via        | pkill -x (applications_core); aqui:
          | contrato de escritorio solo para ventanas propias               | cierre via contrato solo propio

Estado de verificacion: Windows se verifica en real con las suites del roadmap;
macOS queda NO VERIFICADO (sin equipo) hasta la FASE 22.

LIMITACIONES CONOCIDAS / PENDIENTE PARA FASES POSTERIORES
* La desambiguacion devuelve ``needs_clarification`` con candidatos, pero el
  dialogo con el usuario es la FASE 4 (4.5.7).
* La seleccion de monitor y la calibracion tras abrir pertenecen al pipeline
  de calibracion (3.8.6.13/3.8.6.14) y a la capability ``calibrate`` (FASE 12).
* Login y recursos se toman del conocimiento declarado; el preflight general
  (FASE 11) los ampliara.
* El aprendizaje de costes/uso real de aplicaciones es la FASE 18.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.core.operation_errors import (
    ErrorCode,
    IdempotencyRegistry,
    OperationError,
    OperationStage,
    RetryPolicy,
    get_idempotency_registry,
    redact_evidence,
    redact_text,
)
from src.desktop.platform_contract import (
    Capability,
    CapabilityReport,
    CapabilityStatus,
    WindowInfo,
)

logger = get_logger(__name__)


# ============================================================================
# TIPOS DE DESTINO
# ============================================================================

TARGET_EXE = "exe"
TARGET_LNK = "lnk"
TARGET_AUMID = "aumid"
TARGET_URI = "uri"
TARGET_BUNDLE = "bundle"
TARGET_URL = "url"
# Nombre de comando sin ruta (p. ej. "chrome") que el SO resuelve por PATH al
# crear el proceso. Se lanza como argv de un solo elemento, nunca por shell.
TARGET_COMMAND = "command"

TARGET_TYPES = frozenset({
    TARGET_EXE, TARGET_LNK, TARGET_AUMID, TARGET_URI, TARGET_BUNDLE, TARGET_URL, TARGET_COMMAND,
})

# Esquemas URI admitidos por defecto como lanzamiento (coinciden con los de
# ApplicationPreflight._URI_SCHEMES). Cualquier otro se rechaza.
DEFAULT_ALLOWED_URI_SCHEMES = frozenset({
    "ms-settings", "microsoft-edge", "ms-store", "ms-windows-store", "mailto", "http", "https",
})

# Caracteres que nunca deben aparecer en un nombre de aplicacion pedido por el
# usuario ni en un destino: controles y separadores de comandos de shell.
_UNSAFE_CHARS = re.compile(r"[\x00-\x1f\x7f]|[;&|`$<>]")

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"
RESOLUTION_ERROR = "error"


def is_safe_launch_text(value: str) -> bool:
    """True si el texto no contiene controles ni metacaracteres de shell."""
    if not isinstance(value, str) or not value.strip():
        return False
    return _UNSAFE_CHARS.search(value) is None


def uri_scheme(value: str) -> Optional[str]:
    """Esquema URI de ``value`` o None (las rutas con unidad no son URI)."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) >= 2 and text[0].isalpha() and text[1] == ":":
        return None
    if text.startswith("\\\\"):
        return None
    match = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", text)
    return match.group(1).lower() if match else None


def expected_process_names(executable: str) -> List[str]:
    """Nombres de proceso esperados para un ejecutable o comando.

    En Windows un comando sin extension (``chrome``) corre como ``chrome.exe``.
    """
    base = os.path.basename(str(executable or "").replace("\\", "/")).strip()
    if not base:
        return []
    names = [base]
    if sys.platform == "win32" and not base.casefold().endswith(".exe"):
        names.append(base + ".exe")
    return names


def normalize_app_key(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


@dataclass
class LaunchTarget:
    """Destino de lanzamiento resuelto en el equipo actual.

    ``target`` (ruta, AUMID, bundle id, URI o URL) es un dato privado: nunca se
    escribe en logs sin ``redact_evidence``. ``identity`` es la identidad
    estable (catalogo global), independiente de la ruta.
    """

    identity: str
    display_name: str
    target_type: str
    target: str
    platform: str
    source: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    app_id: str = ""
    process_names: List[str] = field(default_factory=list)
    catalog_entity_id: Optional[str] = None
    machine_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Representacion redactada (apta para logs y evidencia)."""
        return redact_evidence({
            "identity": self.identity,
            "display_name": self.display_name,
            "target_type": self.target_type,
            "target": self.target,
            "platform": self.platform,
            "source": self.source,
            "app_id": self.app_id,
            "process_names": list(self.process_names),
            "catalog_entity_id": self.catalog_entity_id,
            "machine_id": self.machine_id,
            "evidence": dict(self.evidence),
        })


@dataclass
class ResolutionOutcome:
    """Resultado de resolver un nombre a un destino local."""

    status: str
    target: Optional[LaunchTarget] = None
    candidates: List[LaunchTarget] = field(default_factory=list)
    error: Optional[OperationError] = None
    source: str = ""

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED and self.target is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "target": self.target.to_dict() if self.target else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "error": self.error.to_dict() if self.error else None,
            "source": self.source,
        }


@dataclass
class LaunchPreflight:
    """Decision del preflight sobre un destino concreto (no lanza nada)."""

    allowed: bool
    reason: str
    blocked_by: Optional[str] = None
    requires_elevation: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return redact_evidence({
            "allowed": self.allowed,
            "reason": self.reason,
            "blocked_by": self.blocked_by,
            "requires_elevation": self.requires_elevation,
            "details": dict(self.details),
        })

    @classmethod
    def from_preflight_dict(cls, result: Any) -> "LaunchPreflight":
        data = result if isinstance(result, dict) else getattr(result, "to_dict", lambda: {})()
        if not isinstance(data, dict):
            data = {}
        return cls(
            allowed=bool(data.get("allowed", False)),
            reason=str(data.get("reason", "") or ""),
            blocked_by=data.get("blocked_by"),
            requires_elevation=bool(data.get("requires_elevation", False)),
            details={k: v for k, v in data.items() if k not in ("allowed", "reason", "blocked_by")},
        )


@dataclass
class LaunchOutcome:
    """Resultado de abrir (o reutilizar) una aplicacion."""

    success: bool
    pid: Optional[int] = None
    window: Optional[WindowInfo] = None
    reused_existing: bool = False
    target: Optional[LaunchTarget] = None
    error: Optional[OperationError] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    launched: bool = False
    process_verified: bool = False
    window_verified: bool = False
    attempts: int = 0
    app_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "pid": self.pid,
            "window": _objeto_a_dict(self.window),
            "reused_existing": self.reused_existing,
            "target": _objeto_a_dict(self.target),
            "error": _objeto_a_dict(self.error),
            "evidence": redact_evidence(dict(self.evidence)),
            "launched": self.launched,
            "process_verified": self.process_verified,
            "window_verified": self.window_verified,
            "attempts": self.attempts,
            "app_name": self.app_name,
        }

    @classmethod
    def failed(
        cls,
        error: OperationError,
        target: Optional[LaunchTarget] = None,
        app_name: str = "",
        **evidence: Any,
    ) -> "LaunchOutcome":
        return cls(False, target=target, error=error, app_name=app_name, evidence=dict(evidence))


# ============================================================================
# CONTRATO DEL ADAPTADOR
# ============================================================================


def _objeto_a_dict(valor: Any) -> Optional[Dict[str, Any]]:
    """Serializa ventana/destino/error del resultado sin perder datos.

    Los tipos del contrato (`WindowInfo`, `LaunchTarget`, `OperationError`)
    tienen `to_dict()`. Un adaptador que devuelva otro objeto (p. ej. un
    `SimpleNamespace`) se serializa con sus atributos, redactados, en lugar de
    descartarse en silencio como None.
    """
    if valor is None:
        return None
    to_dict = getattr(valor, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(valor, dict):
        return redact_evidence(dict(valor))
    atributos = getattr(valor, "__dict__", None)
    if isinstance(atributos, dict):
        return redact_evidence({k: v for k, v in atributos.items() if not k.startswith("_")})
    return {"valor": redact_text(str(valor))}


def _default_spawner(argv: Sequence[str]) -> Any:
    import subprocess

    return subprocess.Popen(list(argv), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _default_url_opener(url: str) -> bool:
    import webbrowser

    return bool(webbrowser.open(url))


def _pid_of(handle: Any) -> Optional[int]:
    pid = getattr(handle, "pid", None)
    if isinstance(pid, bool):
        return None
    if isinstance(pid, int) and pid > 0:
        return pid
    return None


class ApplicationLaunchAdapter:
    """Contrato de descubrimiento/lanzamiento de un SO.

    Las subclases implementan ``discover``, ``resolve``, ``preflight`` y los
    tipos de destino propios de su SO en ``launch``. ``verify`` y el
    lanzamiento de ``exe``/``command``/``url`` son comunes.
    """

    platform_name: str = ""

    def __init__(self, desktop: Any = None, poll_interval: float = 0.25) -> None:
        self._desktop = desktop
        self.poll_interval = max(0.05, float(poll_interval))

    # ------------------------------------------------------------------
    # Contrato
    # ------------------------------------------------------------------

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        return {
            cap: CapabilityReport(cap, CapabilityStatus.NO_SOPORTADO, "adaptador base")
            for cap in (
                Capability.DISCOVER, Capability.RESOLVE, Capability.PREFLIGHT,
                Capability.LAUNCH, Capability.PROCESS_VERIFY, Capability.WINDOW_VERIFY,
            )
        }

    def discover(self, name: str) -> List[LaunchTarget]:
        return []

    def resolve(self, name: str) -> ResolutionOutcome:
        return ResolutionOutcome(
            NOT_FOUND,
            error=OperationError(
                OperationStage.RESOLUTION, ErrorCode.NOT_SUPPORTED,
                "El adaptador %s no resuelve aplicaciones" % (self.platform_name or "base"),
            ),
        )

    def preflight(self, target: LaunchTarget) -> LaunchPreflight:
        return LaunchPreflight(False, "Preflight no disponible en este adaptador", "adapter_missing")

    def launch(
        self,
        target: LaunchTarget,
        timeout: float = 15.0,
        spawner: Optional[Callable[[Sequence[str]], Any]] = None,
        url_opener: Optional[Callable[[str], bool]] = None,
    ) -> LaunchOutcome:
        """Lanza un destino YA aprobado por el preflight. No verifica ventana."""
        spawn = spawner or _default_spawner
        open_url = url_opener or _default_url_opener
        started = time.time()
        preexisting = self._pids_by_names(target.process_names)
        windows_before = self._snapshot_window_ids() if preexisting else None
        try:
            if target.target_type in (TARGET_EXE, TARGET_COMMAND):
                if not is_safe_launch_text(target.target):
                    return LaunchOutcome.failed(
                        OperationError(OperationStage.LAUNCH, ErrorCode.UNSAFE_ARGUMENT,
                                       "Destino de lanzamiento con caracteres no admitidos"),
                        target, target.display_name,
                    )
                if target.target_type == TARGET_EXE and not os.path.isfile(target.target):
                    return LaunchOutcome.failed(
                        OperationError(OperationStage.LAUNCH, ErrorCode.TARGET_NOT_LOCALIZABLE,
                                       "El ejecutable resuelto ya no existe en este equipo",
                                       evidence={"target": target.target}),
                        target, target.display_name,
                    )
                handle = spawn([target.target])
                evidence = {"launch_started_at": started, "preexisting_pids": sorted(preexisting),
                            "mechanism": "process_argv"}
                if windows_before is not None:
                    evidence["preexisting_window_ids"] = windows_before
                return LaunchOutcome(
                    True, pid=_pid_of(handle), target=target, launched=True,
                    app_name=target.display_name,
                    evidence=evidence,
                )
            if target.target_type == TARGET_URL:
                scheme = uri_scheme(target.target)
                if scheme not in ("http", "https"):
                    return LaunchOutcome.failed(
                        OperationError(OperationStage.LAUNCH, ErrorCode.UNSUPPORTED_URI,
                                       "Solo se abren URL http/https como destino web"),
                        target, target.display_name,
                    )
                if not open_url(target.target):
                    return LaunchOutcome.failed(
                        OperationError(OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED,
                                       "No se pudo abrir la URL de %s" % target.display_name),
                        target, target.display_name,
                    )
                return LaunchOutcome(
                    True, target=target, launched=True, app_name=target.display_name,
                    evidence={"launch_started_at": started, "mechanism": "default_browser"},
                )
        except FileNotFoundError as exc:
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.TARGET_NOT_LOCALIZABLE,
                               "El SO no encontro el destino de %s: %s" % (target.display_name, exc)),
                target, target.display_name,
            )
        except PermissionError as exc:
            return LaunchOutcome.failed(
                OperationError(OperationStage.PERMISSION, ErrorCode.PERMISSION_DENIED,
                               "Permiso denegado al lanzar %s: %s" % (target.display_name, exc)),
                target, target.display_name,
            )
        except OSError as exc:
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED,
                               "Fallo al lanzar %s: %s" % (target.display_name, exc)),
                target, target.display_name,
            )
        return LaunchOutcome.failed(
            OperationError(OperationStage.LAUNCH, ErrorCode.NOT_SUPPORTED,
                           "Tipo de destino %s no soportado por el adaptador %s"
                           % (target.target_type, self.platform_name or "base")),
            target, target.display_name,
        )

    def verify(
        self,
        pid: Optional[int],
        identity: Any = None,
        timeout: float = 10.0,
        launch_started_at: Optional[float] = None,
        preexisting_pids: Optional[Sequence[int]] = None,
        preexisting_window_ids: Optional[Sequence[int]] = None,
    ) -> LaunchOutcome:
        """Verifica proceso y ventana visible con espera acotada (sin sleep fijo).

        Ultimo recurso para lanzadores sin PID ni nombre de proceso conocido
        (AUMID, URI): una ventana visible NUEVA (no presente en
        ``preexisting_window_ids``) cuyo titulo contiene el nombre visible de la
        aplicacion; se marca en la evidencia como coincidencia por titulo.

        Si el PID del lanzador termina pronto (accesos directos, AUMID,
        aplicaciones de instancia unica), se buscan procesos NUEVOS con el
        nombre esperado (creados despues del lanzamiento y que no existian
        antes) y sus ventanas.
        """
        target = identity if isinstance(identity, LaunchTarget) else None
        names = list(target.process_names) if target else []
        before = set(int(p) for p in (preexisting_pids or []))
        deadline = time.monotonic() + max(0.0, float(timeout))
        desktop = self._get_desktop()
        last_pids: List[int] = []
        process_ok = False
        while True:
            pids: List[int] = []
            if pid and self._pid_alive(pid):
                pids.append(int(pid))
            for extra in self._new_pids_by_names(names, before, launch_started_at):
                if extra not in pids:
                    pids.append(extra)
            last_pids = pids
            process_ok = process_ok or bool(pids)
            window = self._first_window(desktop, pids)
            if window is not None:
                return LaunchOutcome(
                    True, pid=window.pid, window=window, target=target, process_verified=True,
                    window_verified=True, evidence={"verified_pids": pids},
                )
            if names and before and preexisting_window_ids is not None:
                # Aplicaciones de instancia unica o con proceso residente
                # (navegadores, Bloc de notas de Windows 11): el lanzador
                # entrega la orden al proceso que ya existia y la ventana nueva
                # pertenece a ese proceso. Solo cuenta una ventana que no
                # existia antes del lanzamiento.
                window = self._new_window_of_pids(
                    desktop, sorted(before & self._pids_by_names(names)), preexisting_window_ids,
                )
                if window is not None:
                    return LaunchOutcome(
                        True, pid=window.pid, window=window, target=target, process_verified=True,
                        window_verified=True,
                        evidence={"verified_pids": [window.pid],
                                  "window_match": "nueva_ventana_de_proceso_existente"},
                    )
            if not pids and not names and preexisting_window_ids is not None and target is not None:
                # Primero por identidad del paquete (AUMID del proceso de la
                # ventana): no depende del idioma ni del titulo. Si el
                # adaptador no puede leerla, por titulo.
                window = self._new_window_by_app_id(desktop, preexisting_window_ids, target.app_id)
                if window is not None:
                    return LaunchOutcome(
                        True, pid=window.pid, window=window, target=target, process_verified=True,
                        window_verified=True,
                        evidence={"verified_pids": [window.pid], "window_match": "nueva_ventana_por_aumid"},
                    )
                window = self._new_window_by_title(desktop, preexisting_window_ids, target.display_name)
                if window is not None:
                    return LaunchOutcome(
                        True, pid=window.pid, window=window, target=target, process_verified=True,
                        window_verified=True,
                        evidence={"verified_pids": [window.pid], "window_match": "nueva_ventana_por_titulo"},
                    )
            if time.monotonic() >= deadline:
                break
            time.sleep(self.poll_interval)
        if desktop is None:
            return LaunchOutcome(
                process_ok, pid=last_pids[0] if last_pids else pid, target=target,
                process_verified=process_ok, window_verified=False,
                error=None if process_ok else OperationError(
                    OperationStage.PROCESS, ErrorCode.PROCESS_NOT_FOUND,
                    "No se encontro el proceso lanzado"),
                evidence={"window_verification": "no_disponible", "verified_pids": last_pids},
            )
        if process_ok:
            return LaunchOutcome(
                False, pid=last_pids[0] if last_pids else pid, target=target, process_verified=True,
                window_verified=False,
                error=OperationError(OperationStage.WINDOW, ErrorCode.WINDOW_NOT_FOUND,
                                     "El proceso esta en ejecucion pero no aparecio una ventana visible "
                                     "en %.1f s" % timeout),
                evidence={"verified_pids": last_pids},
            )
        return LaunchOutcome(
            False, pid=pid, target=target,
            error=OperationError(OperationStage.PROCESS, ErrorCode.PROCESS_NOT_FOUND,
                                 "El proceso lanzado no esta en ejecucion"),
            evidence={"verified_pids": []},
        )

    def find_running(self, target: LaunchTarget) -> List[int]:
        """PIDs en ejecucion del destino (por nombre de proceso esperado)."""
        return sorted(self._pids_by_names(target.process_names))

    def find_windows_for_pids(self, pids: Sequence[int]) -> Optional[WindowInfo]:
        return self._first_window(self._get_desktop(), list(pids))

    # ------------------------------------------------------------------
    # Ayudas comunes
    # ------------------------------------------------------------------

    def _get_desktop(self) -> Any:
        if self._desktop is not None:
            return self._desktop
        try:
            from src.desktop.platform_contract import get_desktop_platform

            self._desktop = get_desktop_platform()
        except Exception as exc:
            logger.warning("Contrato de escritorio no disponible para verificar ventanas: %s", exc)
            self._desktop = None
        return self._desktop

    @staticmethod
    def _first_window(desktop: Any, pids: Sequence[int]) -> Optional[WindowInfo]:
        if desktop is None:
            return None
        for pid in pids:
            try:
                result = desktop.list_windows(pid=int(pid), visible_only=True)
            except Exception as exc:
                logger.debug("list_windows(pid=%s) fallo: %s", pid, exc)
                continue
            if getattr(result, "ok", False) and result.value:
                for window in result.value:
                    if getattr(window, "is_visible", False) and not getattr(window, "is_minimized", False):
                        return window
                return result.value[0]
        return None

    def _snapshot_window_ids(self) -> List[int]:
        """Identificadores de las ventanas visibles antes de lanzar."""
        desktop = self._get_desktop()
        if desktop is None:
            return []
        try:
            result = desktop.list_windows(visible_only=True)
            if getattr(result, "ok", False):
                return [int(w.window_id) for w in (result.value or [])]
        except Exception as exc:
            logger.debug("No se pudo tomar la instantanea de ventanas: %s", exc)
        return []

    @staticmethod
    def _new_window_of_pids(
        desktop: Any, pids: Sequence[int], before_window_ids: Sequence[int]
    ) -> Optional[WindowInfo]:
        """Primera ventana visible de `pids` que no estaba en `before_window_ids`."""
        if desktop is None or not pids:
            return None
        known = set(int(w) for w in before_window_ids)
        for pid in pids:
            try:
                result = desktop.list_windows(pid=int(pid), visible_only=True)
            except Exception as exc:
                logger.debug("list_windows(pid=%s) fallo: %s", pid, exc)
                continue
            if not getattr(result, "ok", False):
                continue
            for window in result.value or []:
                if int(window.window_id) in known:
                    continue
                if getattr(window, "is_visible", False) and not getattr(window, "is_minimized", False):
                    return window
        return None

    def _new_window_by_app_id(
        self, desktop: Any, before: Sequence[int], app_id: str
    ) -> Optional[WindowInfo]:
        """Ventana nueva cuyo proceso tiene el AUMID ``app_id``.

        El contrato base no sabe leer la identidad de paquete de un proceso:
        devuelve None y la verificacion sigue por titulo. Lo implementa el
        adaptador de Windows.
        """
        return None

    @staticmethod
    def _new_window_by_title(desktop: Any, before: Sequence[int], display_name: str) -> Optional[WindowInfo]:
        if desktop is None or not display_name:
            return None
        known = set(int(w) for w in before)
        wanted = display_name.strip().casefold()
        try:
            result = desktop.list_windows(visible_only=True)
        except Exception as exc:
            logger.debug("list_windows() fallo: %s", exc)
            return None
        if not getattr(result, "ok", False):
            return None
        for window in result.value or []:
            if int(window.window_id) in known:
                continue
            if wanted and wanted in str(getattr(window, "title", "") or "").casefold():
                return window
        return None

    @staticmethod
    def _pid_alive(pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            import psutil

            if not psutil.pid_exists(int(pid)):
                return False
            proc = psutil.Process(int(pid))
            return proc.status() != getattr(psutil, "STATUS_ZOMBIE", "zombie")
        except Exception as exc:
            logger.debug("_pid_alive(%s): %s", pid, exc)
            return False

    @staticmethod
    def _pids_by_names(names: Sequence[str]) -> set:
        wanted = {str(n).casefold() for n in names if n}
        if not wanted:
            return set()
        result = set()
        try:
            import psutil

            for proc in psutil.process_iter(["pid", "name"]):
                pname = str(proc.info.get("name") or "").casefold()
                if pname in wanted:
                    result.add(int(proc.info["pid"]))
        except Exception as exc:
            logger.debug("_pids_by_names: %s", exc)
        return result

    @staticmethod
    def _new_pids_by_names(
        names: Sequence[str],
        before: set,
        launch_started_at: Optional[float],
    ) -> List[int]:
        wanted = {str(n).casefold() for n in names if n}
        if not wanted:
            return []
        found: List[int] = []
        try:
            import psutil

            for proc in psutil.process_iter(["pid", "name", "create_time"]):
                pname = str(proc.info.get("name") or "").casefold()
                pid = int(proc.info["pid"])
                if pname not in wanted or pid in before:
                    continue
                created = proc.info.get("create_time")
                if launch_started_at is not None and created is not None and created < launch_started_at - 2.0:
                    continue
                found.append(pid)
        except Exception as exc:
            logger.debug("_new_pids_by_names: %s", exc)
        return found


class UnsupportedLaunchAdapter(ApplicationLaunchAdapter):
    """Adaptador para un SO sin soporte: todo devuelve NOT_SUPPORTED explicito."""

    def __init__(self, platform: str) -> None:
        super().__init__(desktop=None)
        self.platform_name = platform

    def launch(self, target: LaunchTarget, timeout: float = 15.0, spawner=None, url_opener=None) -> LaunchOutcome:
        return LaunchOutcome.failed(
            OperationError(OperationStage.LAUNCH, ErrorCode.ADAPTER_MISSING,
                           "No hay adaptador de lanzamiento para el SO %s" % self.platform_name),
            target, target.display_name,
        )


def get_launch_adapter(platform: Optional[str] = None, app_manager: Any = None, desktop: Any = None) -> ApplicationLaunchAdapter:
    """Adaptador de lanzamiento del SO actual (nuevo en cada llamada).

    En un SO sin adaptador devuelve ``UnsupportedLaunchAdapter`` (todas sus
    operaciones fallan con ``adapter_missing``/``not_supported``); nunca usa el
    adaptador de otro SO.
    """
    plat = platform or sys.platform
    if plat == "win32":
        from src.hands.apps.launch_windows import WindowsLaunchAdapter

        return WindowsLaunchAdapter(app_manager=app_manager, desktop=desktop)
    if plat == "darwin":
        from src.hands.apps.launch_macos import MacOSLaunchAdapter

        return MacOSLaunchAdapter(app_manager=app_manager, desktop=desktop)
    logger.warning("No hay adaptador de lanzamiento para el SO %s", plat)
    return UnsupportedLaunchAdapter(plat)


# ============================================================================
# SERVICIO UNICO DE APERTURA
# ============================================================================


class ApplicationLaunchService:
    """Flujo unico de apertura y cierre de aplicaciones.

    Dependencias inyectables (las usa ``applications_core.open_application``
    para conservar sus puntos de extension): ``app_manager`` (catalogo global),
    ``preflight`` (``ApplicationPreflight``), ``process_spawner(argv)``,
    ``url_opener(url)``, ``availability_checker(app)`` e
    ``is_open_checker(app_name, app)``.
    """

    OPEN_KEY_PREFIX = "open_application:"

    def __init__(
        self,
        adapter: Optional[ApplicationLaunchAdapter] = None,
        desktop: Any = None,
        retry_policy: Optional[RetryPolicy] = None,
        app_manager: Any = None,
        preflight: Any = None,
        process_spawner: Optional[Callable[[Sequence[str]], Any]] = None,
        url_opener: Optional[Callable[[str], bool]] = None,
        availability_checker: Optional[Callable[[Any], bool]] = None,
        is_open_checker: Optional[Callable[[str, Any], bool]] = None,
        verify_window: bool = True,
        discovery_fallback: bool = True,
        registry: Optional[IdempotencyRegistry] = None,
    ) -> None:
        self._adapter = adapter
        self._desktop = desktop
        self.registry = registry or get_idempotency_registry()
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=2, base_delay=0.5, max_delay=2.0,
                                                        registry=self.registry)
        self._app_manager = app_manager
        self._preflight = preflight
        self._spawner = process_spawner
        self._url_opener = url_opener
        self._availability_checker = availability_checker
        self._is_open_checker = is_open_checker
        self.verify_window = bool(verify_window)
        self.discovery_fallback = bool(discovery_fallback)
        self._owned_lock = threading.Lock()
        self._owned: Dict[str, List[int]] = {}
        # Ventanas concretas verificadas al abrir (las unicas que close() cierra).
        self._owned_windows: Dict[str, List[int]] = {}

    # ------------------------------------------------------------------
    # Dependencias perezosas
    # ------------------------------------------------------------------

    @property
    def adapter(self) -> ApplicationLaunchAdapter:
        if self._adapter is None:
            self._adapter = get_launch_adapter(app_manager=self._app_manager, desktop=self._desktop)
        return self._adapter

    @property
    def app_manager(self) -> Any:
        if self._app_manager is None:
            from src.hands.apps.applications_core import get_application_manager

            self._app_manager = get_application_manager()
        return self._app_manager

    @property
    def preflight(self) -> Any:
        if self._preflight is None:
            from src.hands.apps.application_preflight import get_application_preflight

            self._preflight = get_application_preflight()
        return self._preflight

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def open(self, app_name: str, timeout: float = 15.0) -> LaunchOutcome:
        """Abre (o reutiliza) una aplicacion por nombre por el flujo unico."""
        name = str(app_name or "").strip()
        if not name or not is_safe_launch_text(name):
            return LaunchOutcome.failed(
                OperationError(OperationStage.RESOLUTION, ErrorCode.INVALID_ARGUMENT,
                               "Nombre de aplicacion vacio o con caracteres no admitidos"),
                app_name=name,
            )
        key = self.OPEN_KEY_PREFIX + normalize_app_key(name)
        done, cached = self.registry.get(key)
        if done and isinstance(cached, LaunchOutcome):
            logger.info("open_application: apertura previa vigente de %s; no se repite", redact_text(name))
            return LaunchOutcome(
                True, pid=cached.pid, window=cached.window, reused_existing=True, target=cached.target,
                evidence={"idempotent_reuse": True}, process_verified=cached.process_verified,
                window_verified=cached.window_verified, app_name=name,
            )

        catalog_app = self._catalog_lookup(name)
        if catalog_app is not None:
            plan = self._plan_catalog_app(name, catalog_app)
        else:
            plan = self._plan_discovered_app(name)
        if isinstance(plan, LaunchOutcome):
            if plan.success:
                self._remember_success(key, plan)
            return plan
        target = plan
        outcome = self._launch_and_verify(name, target, timeout, key)
        return outcome

    def close(self, app_name: str, only_owned: bool = True) -> LaunchOutcome:
        """Cierra de forma ordenada SOLO las ventanas que este servicio abrio y
        verifico (``only_owned=True``). Nunca fuerza el cierre.

        Se cierran las ventanas concretas registradas al abrir, y solo si siguen
        perteneciendo al proceso propio registrado. No se cierran el resto de
        ventanas de ese proceso: un proceso anfitrion compartido (por ejemplo
        ``ApplicationFrameHost`` de las apps UWP) puede tener ventanas del
        usuario.
        """
        key = normalize_app_key(app_name)
        with self._owned_lock:
            pids = list(self._owned.get(key, []))
            window_ids = list(self._owned_windows.get(key, []))
        if only_owned and not pids:
            return LaunchOutcome.failed(
                OperationError(OperationStage.PROCESS, ErrorCode.NOT_FOUND,
                               "No hay procesos de %s abiertos por JARVIS en esta sesion" % app_name),
                app_name=app_name,
            )
        desktop = self.adapter._get_desktop()
        closed: List[int] = []
        if desktop is not None:
            for window_id in window_ids:
                try:
                    current = desktop.get_window(int(window_id))
                    window = current.value if getattr(current, "ok", False) else None
                    if window is None or int(getattr(window, "pid", 0) or 0) not in pids:
                        continue  # ya cerrada o el identificador ya no es de un proceso propio
                    if getattr(desktop.close_window(int(window_id)), "ok", False):
                        closed.append(int(window_id))
                except Exception as exc:
                    logger.warning("No se pudo cerrar la ventana %s: %s", window_id, exc)
        self.registry.forget(self.OPEN_KEY_PREFIX + key)
        with self._owned_lock:
            self._owned.pop(key, None)
            self._owned_windows.pop(key, None)
        if closed:
            return LaunchOutcome(True, app_name=app_name, evidence={"closed_windows": closed})
        return LaunchOutcome.failed(
            OperationError(OperationStage.WINDOW, ErrorCode.WINDOW_NOT_FOUND,
                           "No se encontraron ventanas propias que cerrar"),
            app_name=app_name,
        )

    # ------------------------------------------------------------------
    # Catalogo global
    # ------------------------------------------------------------------

    def _catalog_lookup(self, name: str) -> Any:
        try:
            return self.app_manager.get_application(name)
        except Exception as exc:
            logger.warning("Consulta del catalogo global fallo para %s: %s", redact_text(name), exc)
            return None

    @staticmethod
    def catalog_preflight_dict(app: Any) -> Dict[str, Any]:
        """Dict del catalogo para ``ApplicationPreflight.check`` (mismo contrato
        que ``applications_core._app_knowledge_to_preflight_dict``)."""
        metadata = getattr(app, "metadata", None) or {}
        return {
            "name": getattr(app, "name", ""),
            "app_id": str(metadata.get("app_id", "") or ""),
            "login_required": getattr(app, "login_required", False),
            "logged_in": metadata.get("logged_in", None),
            "resources_available": metadata.get("resources_available", None),
            "url": getattr(app, "url", None),
        }

    def _is_open(self, name: str, app: Any) -> bool:
        if self._is_open_checker is not None:
            return bool(self._is_open_checker(name, app))
        try:
            return bool(self.app_manager.is_application_open(name))
        except Exception as exc:
            logger.debug("is_application_open(%s) fallo: %s", redact_text(name), exc)
            return False

    def _available(self, app: Any) -> bool:
        if self._availability_checker is not None:
            return bool(self._availability_checker(app))
        executable = str(getattr(app, "executable", None) or "").strip()
        if not executable:
            return bool(getattr(app, "url", None))
        if os.path.isabs(executable) or any(sep in executable for sep in ("/", "\\")):
            return os.path.isfile(executable)
        import shutil

        return shutil.which(executable) is not None

    def _plan_catalog_app(self, name: str, app: Any) -> Any:
        """Devuelve un ``LaunchTarget`` listo para lanzar o un ``LaunchOutcome``
        terminal (error, o reutilizacion de la instancia abierta)."""
        display = str(getattr(app, "name", name) or name)
        metadata = getattr(app, "metadata", None) or {}
        entity_id = metadata.get("entity_id")
        preflight_raw = self.preflight.check(self.catalog_preflight_dict(app))
        decision = LaunchPreflight.from_preflight_dict(preflight_raw)
        # Cuando el preflight no resuelve un ejecutable para el nombre del
        # catalogo (a menudo localizado) y la entidad no trae un destino propio
        # verificable en este equipo, se intenta la resolucion local por nombre
        # (PATH, shell:AppsFolder, registro, App Paths) antes de rechazarla.
        resolver_localmente = False
        if not decision.allowed:
            executable = str(getattr(app, "executable", None) or "").strip()
            url = str(getattr(app, "url", None) or "").strip()
            comando_sin_ruta = bool(executable) and not os.path.isabs(executable) and "/" not in executable and "\\" not in executable
            if ((not executable and not url) or comando_sin_ruta) and decision.blocked_by == "executable_not_resolved":
                resolver_localmente = True
                logger.debug(
                    "Catalogo %s sin destino propio verificable en este equipo; se intenta resolucion local para %s",
                    display, name,
                )
            else:
                code = ErrorCode.ELEVATION_REQUIRED if decision.requires_elevation else ErrorCode.PREFLIGHT_BLOCKED
                return LaunchOutcome.failed(
                    OperationError(
                        OperationStage.PREFLIGHT, code,
                        "La aplicacion %s no paso el preflight: %s (bloqueado por: %s)"
                        % (display, decision.reason or "sin motivo", decision.blocked_by or "desconocido"),
                        evidence={"preflight": decision.to_dict()},
                    ),
                    app_name=display,
                )

        # Ruta del ejecutable que el propio preflight resolvio y valido en este
        # equipo (shell:AppsFolder, inventario por machine_id, PATH o App Paths).
        preflight_path = str(decision.details.get("executable_path") or "").strip()
        if preflight_path and not os.path.isfile(preflight_path):
            preflight_path = ""

        requirements = list(getattr(app, "preflight_requirements", None) or [])
        if ("application_available" in requirements and not self._available(app)
                and not preflight_path):
            return LaunchOutcome.failed(
                OperationError(OperationStage.RESOLUTION, ErrorCode.NOT_INSTALLED,
                               "La aplicacion %s no esta disponible" % display),
                app_name=display,
            )

        if self._is_open(name, app):
            open_cap = None
            try:
                open_cap = app.get_capability("open")
            except Exception as exc:
                logger.debug("get_capability(open) fallo: %s", exc)
            preconditions = list(getattr(open_cap, "preconditions", None) or []) if open_cap else []
            if any("closed" in str(p).lower() for p in preconditions):
                return LaunchOutcome.failed(
                    OperationError(
                        OperationStage.PREFLIGHT, ErrorCode.ALREADY_OPEN_REQUIRES_CLOSED,
                        "La aplicacion %s ya esta abierta pero su contrato requiere cerrarla "
                        "primero (precondiciones: %s)" % (display, preconditions),
                    ),
                    app_name=display,
                )
            window = self._existing_window_for(app)
            if window is not None or not self._running_without_window(app):
                return LaunchOutcome(
                    True, pid=window.pid if window else None, window=window, reused_existing=True,
                    app_name=display, process_verified=True, window_verified=window is not None,
                    evidence={"reuse": "instancia_existente", "preflight": decision.to_dict()},
                )
            # Procesos reales con el nombre esperado y ninguna ventana visible
            # (navegador en segundo plano, arranque rapido): no hay ventana que
            # reutilizar; se lanza y la verificacion busca la ventana nueva.
            logger.info("%s esta en ejecucion sin ventana visible; se abre una ventana nueva", display)

        if resolver_localmente:
            resolution = self._resolve_locally(name)
            if not resolution.resolved:
                if resolution.status == AMBIGUOUS:
                    return self._ambiguity_outcome(display, resolution)
                return self._catalog_unresolved_outcome(display, app, resolution, decision)
            target = resolution.target
            assert target is not None
            if entity_id and not target.catalog_entity_id:
                target.catalog_entity_id = entity_id
            gate = self._target_preflight(target)
            if isinstance(gate, LaunchOutcome):
                return gate
            return target

        executable = str(getattr(app, "executable", None) or "").strip()
        url = str(getattr(app, "url", None) or "").strip()
        if executable:
            if not is_safe_launch_text(executable):
                return LaunchOutcome.failed(
                    OperationError(OperationStage.PREFLIGHT, ErrorCode.UNSAFE_ARGUMENT,
                                   "El ejecutable configurado de %s contiene caracteres no admitidos" % display),
                    app_name=display,
                )
            is_path = os.path.isabs(executable) or any(sep in executable for sep in ("/", "\\"))
            if is_path:
                localizable = os.path.isfile(executable)
            else:
                import shutil

                localizable = shutil.which(executable) is not None
            if not localizable and preflight_path and is_safe_launch_text(preflight_path):
                # El catalogo guarda un comando ("chrome") que CreateProcess no
                # encuentra fuera de PATH: se lanza la ruta concreta que el
                # preflight resolvio y valido en este equipo.
                return LaunchTarget(
                    identity=str(entity_id or "catalogo:%s" % normalize_app_key(display)),
                    display_name=display,
                    target_type=TARGET_EXE,
                    target=preflight_path,
                    platform=sys.platform,
                    source="catalogo_global+preflight",
                    app_id=str(metadata.get("app_id", "") or ""),
                    process_names=expected_process_names(preflight_path),
                    catalog_entity_id=entity_id,
                    evidence={"preflight": decision.to_dict()},
                )
            return LaunchTarget(
                identity=str(entity_id or "catalogo:%s" % normalize_app_key(display)),
                display_name=display,
                target_type=TARGET_EXE if is_path else TARGET_COMMAND,
                target=executable,
                platform=sys.platform,
                source="catalogo_global",
                app_id=str(metadata.get("app_id", "") or ""),
                process_names=expected_process_names(executable),
                catalog_entity_id=entity_id,
                evidence={"preflight": decision.to_dict()},
            )
        if url:
            return LaunchTarget(
                identity=str(entity_id or "catalogo:%s" % normalize_app_key(display)),
                display_name=display,
                target_type=TARGET_URL,
                target=url,
                platform=sys.platform,
                source="catalogo_global",
                catalog_entity_id=entity_id,
                evidence={"preflight": decision.to_dict()},
            )

        # Entidad del catalogo sin ejecutable ni URL (p. ej. auto-registrada por
        # el descubrimiento): el destino SOLO se obtiene de la resolucion local
        # por machine_id; nunca de la ruta observada guardada en el catalogo.
        resolution = self._resolve_locally(name)
        if not resolution.resolved:
            if resolution.status == AMBIGUOUS:
                return self._ambiguity_outcome(display, resolution)
            return self._catalog_unresolved_outcome(display, app, resolution, decision)
        target = resolution.target
        assert target is not None
        if entity_id and not target.catalog_entity_id:
            target.catalog_entity_id = entity_id
        gate = self._target_preflight(target)
        if isinstance(gate, LaunchOutcome):
            return gate
        return target

    @staticmethod
    def _catalog_unresolved_outcome(
        display: str, app: Any, resolution: ResolutionOutcome, decision: LaunchPreflight,
    ) -> LaunchOutcome:
        """Error de una aplicacion del catalogo cuya resolucion local no encontro
        destino en este equipo.

        La aplicacion SI existe en el catalogo, asi que no se informa "no
        encontrada": si tiene un comando configurado que el preflight no
        resolvio, se devuelve ese rechazo del preflight; si no tiene ejecutable
        ni URL, se dice asi. La resolucion local queda en la evidencia. Un fallo
        interno de la resolucion (fuentes de descubrimiento caidas, adaptador
        ausente, nombre no admitido) se devuelve tal cual, porque no prueba que
        la aplicacion falte en este equipo.
        """
        error = resolution.error
        ausente = resolution.status == NOT_FOUND and (
            error is None or error.code in (ErrorCode.NOT_INSTALLED, ErrorCode.NOT_FOUND)
        )
        if not ausente and error is not None:
            return LaunchOutcome.failed(error, app_name=display)
        evidence = {"preflight": decision.to_dict(), "resolution": resolution.to_dict()}
        executable = str(getattr(app, "executable", None) or "").strip()
        url = str(getattr(app, "url", None) or "").strip()
        if executable and not decision.allowed:
            code = ErrorCode.ELEVATION_REQUIRED if decision.requires_elevation else ErrorCode.PREFLIGHT_BLOCKED
            return LaunchOutcome.failed(
                OperationError(
                    OperationStage.PREFLIGHT, code,
                    "La aplicacion %s no paso el preflight: %s (bloqueado por: %s)"
                    % (display, decision.reason or "sin motivo", decision.blocked_by or "desconocido"),
                    evidence=evidence,
                ),
                app_name=display,
            )
        if not executable and not url:
            message = ("La aplicacion %s no tiene ejecutable ni URL configurados y no se localizo "
                       "un destino en este equipo" % display)
        else:
            message = "No se localizo un destino de la aplicacion %s en este equipo" % display
        return LaunchOutcome.failed(
            OperationError(OperationStage.RESOLUTION, ErrorCode.TARGET_NOT_LOCALIZABLE, message,
                           evidence=evidence),
            app_name=display,
        )

    def _running_without_window(self, app: Any) -> bool:
        """True solo si hay procesos reales con el nombre esperado del
        ejecutable del catalogo, el contrato de escritorio esta disponible y
        ninguno de esos procesos tiene una ventana visible."""
        executable = str(getattr(app, "executable", None) or "").strip()
        if not executable:
            return False
        pids = sorted(ApplicationLaunchAdapter._pids_by_names(expected_process_names(executable)))
        if not pids:
            return False
        try:
            if self.adapter._get_desktop() is None:
                return False
            return self.adapter.find_windows_for_pids(pids) is None
        except Exception as exc:
            logger.debug("No se pudo comprobar la ventana del proceso residente: %s", exc)
            return False

    def _existing_window_for(self, app: Any) -> Optional[WindowInfo]:
        """Ventana visible de una instancia ya abierta (sin esperar)."""
        executable = str(getattr(app, "executable", None) or "").strip()
        if not executable:
            return None
        pids = sorted(ApplicationLaunchAdapter._pids_by_names(expected_process_names(executable)))
        if not pids:
            return None
        try:
            return self.adapter.find_windows_for_pids(pids)
        except Exception as exc:
            logger.debug("No se pudo localizar la ventana existente: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Descubrimiento + resolucion local
    # ------------------------------------------------------------------

    def _resolve_locally(self, name: str) -> ResolutionOutcome:
        if not self.discovery_fallback:
            return ResolutionOutcome(
                NOT_FOUND,
                error=OperationError(OperationStage.RESOLUTION, ErrorCode.NOT_FOUND,
                                     "Aplicacion no encontrada: %s" % name),
            )
        try:
            return self.adapter.resolve(name)
        except Exception as exc:
            logger.exception("Resolucion local fallo para %s", redact_text(name))
            return ResolutionOutcome(
                RESOLUTION_ERROR,
                error=OperationError(OperationStage.RESOLUTION, ErrorCode.INTERNAL,
                                     "Fallo en la resolucion local: %s" % exc, retryable=True),
            )

    def _plan_discovered_app(self, name: str) -> Any:
        resolution = self._resolve_locally(name)
        if resolution.status == AMBIGUOUS:
            return self._ambiguity_outcome(name, resolution)
        if not resolution.resolved:
            error = resolution.error
            if resolution.status == NOT_FOUND or error is None:
                # Ni en el catalogo global ni en este equipo (inventario/fuentes).
                error = OperationError(
                    OperationStage.RESOLUTION, ErrorCode.NOT_FOUND,
                    "Aplicacion no encontrada: %s" % name,
                    evidence={"resolution": resolution.to_dict()},
                )
            return LaunchOutcome.failed(error, app_name=name)
        target = resolution.target
        assert target is not None
        gate = self._target_preflight(target)
        if isinstance(gate, LaunchOutcome):
            return gate
        running = self.adapter.find_running(target)
        if running:
            window = self.adapter.find_windows_for_pids(running)
            if window is not None:
                return LaunchOutcome(
                    True, pid=window.pid, window=window, reused_existing=True,
                    target=target, app_name=target.display_name, process_verified=True,
                    window_verified=True, evidence={"reuse": "instancia_existente"},
                )
            # Procesos residentes sin ventana visible: se lanza para obtener una.
            logger.info(
                "%s esta en ejecucion sin ventana visible; se abre una ventana nueva",
                redact_text(target.display_name),
            )
        return target

    @staticmethod
    def _ambiguity_outcome(name: str, resolution: ResolutionOutcome) -> LaunchOutcome:
        names = []
        for candidate in resolution.candidates:
            label = candidate.display_name or candidate.identity
            if label and label not in names:
                names.append(label)
        return LaunchOutcome.failed(
            OperationError(
                OperationStage.RESOLUTION, ErrorCode.AMBIGUOUS,
                "La aplicacion %s es ambigua: hay varios destinos posibles en este equipo" % name,
                needs_clarification=True,
                candidates=names,
                evidence={"resolution": resolution.to_dict()},
            ),
            app_name=name,
        )

    def _target_preflight(self, target: LaunchTarget) -> Optional[LaunchOutcome]:
        """Preflight obligatorio sobre un destino resuelto (adaptador + politica)."""
        try:
            decision = self.adapter.preflight(target)
        except Exception as exc:
            logger.exception("Preflight del destino fallo")
            decision = LaunchPreflight(False, "Error en preflight: %s" % exc, "preflight_error")
        target.evidence["preflight"] = decision.to_dict()
        if decision.allowed:
            return None
        blocked = str(decision.blocked_by or "")
        if decision.requires_elevation:
            code = ErrorCode.ELEVATION_REQUIRED
        elif blocked.startswith("gatekeeper"):
            code = ErrorCode.GATEKEEPER_BLOCKED
        elif blocked == "unsupported_uri":
            code = ErrorCode.UNSUPPORTED_URI
        elif blocked == "permission_denied":
            code = ErrorCode.PERMISSION_DENIED
        else:
            code = ErrorCode.PREFLIGHT_BLOCKED
        return LaunchOutcome.failed(
            OperationError(
                OperationStage.PERMISSION if code in (ErrorCode.GATEKEEPER_BLOCKED, ErrorCode.PERMISSION_DENIED)
                else OperationStage.PREFLIGHT,
                code,
                "La aplicacion %s no paso el preflight: %s (bloqueado por: %s)"
                % (target.display_name, decision.reason or "sin motivo", blocked or "desconocido"),
                instructions=str(decision.details.get("instructions", "") or ""),
                evidence={"preflight": decision.to_dict(), "target": target.to_dict()},
            ),
            target=target, app_name=target.display_name,
        )

    # ------------------------------------------------------------------
    # Lanzamiento + verificacion
    # ------------------------------------------------------------------

    def _launch_and_verify(self, name: str, target: LaunchTarget, timeout: float, key: str) -> LaunchOutcome:
        launched_holder: Dict[str, LaunchOutcome] = {}

        def attempt() -> LaunchOutcome:
            result = self.adapter.launch(
                target, timeout=timeout, spawner=self._spawner, url_opener=self._url_opener,
            )
            launched_holder["last"] = result
            return result

        def retryable(result: Any) -> bool:
            # Nunca reintentar despues de haber lanzado un proceso (doble instancia).
            if isinstance(result, LaunchOutcome):
                return (not result.launched) and bool(result.error and result.error.retryable)
            return isinstance(result, TimeoutError)

        outcome = self.retry_policy.run(
            attempt,
            is_success=lambda r: isinstance(r, LaunchOutcome) and r.success and r.launched,
            is_retryable=retryable,
            to_error=lambda r: (r.error if isinstance(r, LaunchOutcome) and r.error else OperationError(
                OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED, "No se pudo lanzar %s" % target.display_name)),
            stage=OperationStage.LAUNCH,
        )
        if not outcome.ok:
            failed = launched_holder.get("last") or LaunchOutcome(False, target=target)
            failed.error = outcome.error
            failed.attempts = outcome.attempts
            failed.app_name = target.display_name
            self._log_outcome(failed)
            return failed

        launched: LaunchOutcome = outcome.value
        launched.attempts = outcome.attempts
        launched.app_name = target.display_name
        if target.target_type == TARGET_URL:
            launched.evidence["window_verification"] = "no_aplica_url_navegador"
            launched.success = True
            self._remember_success(key, launched)
            self._log_outcome(launched)
            return launched

        if target.target_type in (TARGET_EXE, TARGET_COMMAND):
            # Un spawner real siempre devuelve PID; sin PID (doble de prueba o
            # spawner externo) no hay nada verificable sin inventar evidencia.
            verifiable = self.verify_window and launched.pid is not None
        else:
            verifiable = self.verify_window and (
                launched.pid is not None
                or bool(target.process_names)
                or launched.evidence.get("preexisting_window_ids") is not None
            )
        if not verifiable:
            launched.evidence["window_verification"] = "no_verificable_sin_pid"
            self._log_outcome(launched)
            return launched

        verification = self.adapter.verify(
            launched.pid,
            target,
            timeout=timeout,
            launch_started_at=launched.evidence.get("launch_started_at"),
            preexisting_pids=launched.evidence.get("preexisting_pids"),
            preexisting_window_ids=launched.evidence.get("preexisting_window_ids"),
        )
        launched.process_verified = verification.process_verified
        launched.window_verified = verification.window_verified
        launched.window = verification.window
        if verification.pid:
            launched.pid = verification.pid
        launched.evidence["verification"] = verification.evidence
        if verification.window_verified:
            launched.success = True
        elif verification.process_verified:
            # El proceso existe pero no se vio ventana: la apertura NO se repite
            # (no es reintentable) y se informa el fallo de verificacion.
            launched.success = False
            launched.error = verification.error
        else:
            launched.success = False
            launched.error = verification.error or OperationError(
                OperationStage.PROCESS, ErrorCode.PROCESS_NOT_FOUND, "El proceso lanzado no esta en ejecucion")
        if launched.success:
            self._remember_success(key, launched)
            preexisting = {int(p) for p in (launched.evidence.get("preexisting_pids") or [])}
            if launched.pid is not None and int(launched.pid) not in preexisting:
                # Un proceso que ya existia (del usuario) nunca pasa a ser propio.
                self._remember_owned(name, launched.pid, launched.window)
        self._log_outcome(launched)
        return launched

    def _remember_success(self, key: str, outcome: LaunchOutcome) -> None:
        pid = outcome.pid
        window_id = int(outcome.window.window_id) if outcome.window is not None else None

        def still_valid(value: Any) -> bool:
            if not (bool(pid) and ApplicationLaunchAdapter._pid_alive(pid)):
                return False
            if window_id is None:
                return True
            # El proceso puede seguir vivo (ApplicationFrameHost, navegador
            # residente) aunque la ventana abierta ya se haya cerrado: en ese
            # caso la apertura previa ya no es reutilizable.
            desktop = self.adapter._get_desktop()
            if desktop is None:
                return True
            try:
                current = desktop.get_window(window_id)
            except Exception as exc:
                logger.debug("get_window(%s) fallo: %s", window_id, exc)
                return False
            return bool(getattr(current, "ok", False) and getattr(current, "value", None) is not None)

        if pid:
            self.registry.mark_success(key, outcome, ttl_seconds=None, still_valid=still_valid)

    def _remember_owned(self, name: str, pid: Optional[int], window: Any = None) -> None:
        if not pid:
            return
        key = normalize_app_key(name)
        with self._owned_lock:
            self._owned.setdefault(key, []).append(int(pid))
            window_id = getattr(window, "window_id", None)
            if window_id is not None:
                self._owned_windows.setdefault(key, []).append(int(window_id))

    @staticmethod
    def _log_outcome(outcome: LaunchOutcome) -> None:
        data = outcome.to_dict()
        if outcome.success:
            logger.info(
                "Apertura de %s: lanzada=%s proceso=%s ventana=%s reutilizada=%s",
                redact_text(outcome.app_name), outcome.launched, outcome.process_verified,
                outcome.window_verified, outcome.reused_existing,
            )
        else:
            logger.warning("Apertura de %s fallida: %s", redact_text(outcome.app_name), data.get("error"))


# ============================================================================
# IDENTIDAD MULTIPLATAFORMA EN EL CATALOGO GLOBAL (3.8.9.6)
# ============================================================================

PLATFORM_IDENTITIES_KEY = "platform_identities"
_ALLOWED_IDENTITY_FIELDS = {
    "windows": ("aumid", "fabricante", "producto", "nombre_proceso"),
    "macos": ("bundle_id", "bundle_name", "nombre_proceso"),
}


def _looks_like_path(value: str) -> bool:
    text = str(value or "")
    if not text:
        return False
    if "/" in text or "\\" in text:
        return True
    return len(text) >= 2 and text[0].isalpha() and text[1] == ":"


def link_platform_identity(
    entity_id_or_name: str,
    platform: str,
    identity: Dict[str, str],
    memory_manager: Any = None,
    app_manager: Any = None,
) -> Tuple[bool, str]:
    """Enlaza en ``data/memory/entities.json`` la identidad de una app logica en un SO.

    Escribe ``properties.platform_identities[<platform>] = {...}`` con solo
    campos de identidad (AUMID, fabricante/producto o bundle id), nunca rutas,
    PID/HWND ni coordenadas. Es un upsert idempotente que conserva el resto de
    la entidad. Devuelve ``(ok, motivo)``.
    """
    plat = str(platform or "").strip().lower()
    if plat not in _ALLOWED_IDENTITY_FIELDS:
        return False, "plataforma no admitida: %s" % plat
    allowed = _ALLOWED_IDENTITY_FIELDS[plat]
    clean: Dict[str, str] = {}
    for key, value in (identity or {}).items():
        if key not in allowed or value in (None, ""):
            continue
        text = str(value).strip()
        if key != "aumid" and _looks_like_path(text):
            return False, "el campo %s parece una ruta; no se guardan rutas en el catalogo" % key
        if key == "aumid" and ("\\" in text or text.count("/") > 0):
            return False, "AUMID con formato de ruta no admitido"
        clean[key] = text
    if not clean:
        return False, "sin campos de identidad validos"

    if memory_manager is None:
        from src.memory.storage import get_memory_manager

        memory_manager = get_memory_manager()
    entity = memory_manager.get_entity(entity_id_or_name)
    if entity is None and app_manager is not None:
        app = app_manager.get_application(entity_id_or_name)
        entity_id = (getattr(app, "metadata", None) or {}).get("entity_id") if app else None
        if entity_id:
            entity = memory_manager.get_entity(entity_id)
    if entity is None:
        return False, "entidad no encontrada en el catalogo global"
    properties = dict(entity.properties or {})
    identities = dict(properties.get(PLATFORM_IDENTITIES_KEY) or {})
    current = dict(identities.get(plat) or {})
    if all(current.get(k) == v for k, v in clean.items()):
        return True, "sin cambios"
    current.update(clean)
    identities[plat] = current
    properties[PLATFORM_IDENTITIES_KEY] = identities
    entity.properties = properties
    try:
        from datetime import datetime

        entity.updated_at = datetime.now().isoformat()
    except Exception as exc:
        logger.debug("No se pudo actualizar updated_at: %s", exc)
    ok = bool(memory_manager.save_entity(entity))
    return ok, "enlazada" if ok else "no se pudo guardar la entidad"


def get_platform_identity(entity: Any, platform: str) -> Dict[str, str]:
    """Identidad de ``entity`` (Entity o dict) para ``platform`` o {}."""
    props = getattr(entity, "properties", None)
    if props is None and isinstance(entity, dict):
        props = entity.get("properties")
    identities = (props or {}).get(PLATFORM_IDENTITIES_KEY) or {}
    return dict(identities.get(str(platform).lower()) or {})


def find_entity_by_platform_identity(
    platform: str,
    field_name: str,
    value: str,
    memory_manager: Any = None,
) -> Optional[Any]:
    """Busca en el catalogo global la entidad de aplicacion con esa identidad."""
    if memory_manager is None:
        from src.memory.storage import get_memory_manager

        memory_manager = get_memory_manager()
    target = str(value or "").strip().casefold()
    if not target:
        return None
    for entity in memory_manager.get_entities_by_type("application") or []:
        ident = get_platform_identity(entity, platform)
        if str(ident.get(field_name, "")).casefold() == target:
            return entity
    return None


__all__ = [
    "TARGET_EXE",
    "TARGET_LNK",
    "TARGET_AUMID",
    "TARGET_URI",
    "TARGET_BUNDLE",
    "TARGET_URL",
    "TARGET_COMMAND",
    "TARGET_TYPES",
    "DEFAULT_ALLOWED_URI_SCHEMES",
    "RESOLVED",
    "AMBIGUOUS",
    "NOT_FOUND",
    "RESOLUTION_ERROR",
    "LaunchTarget",
    "ResolutionOutcome",
    "LaunchPreflight",
    "LaunchOutcome",
    "ApplicationLaunchAdapter",
    "UnsupportedLaunchAdapter",
    "ApplicationLaunchService",
    "get_launch_adapter",
    "is_safe_launch_text",
    "uri_scheme",
    "normalize_app_key",
    "link_platform_identity",
    "get_platform_identity",
    "find_entity_by_platform_identity",
    "PLATFORM_IDENTITIES_KEY",
]
