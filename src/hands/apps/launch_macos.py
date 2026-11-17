"""
Adaptador de descubrimiento y lanzamiento de aplicaciones para macOS.

ESCRITO SIN MAC PARA PROBAR (regla 3 de la cabecera del roadmap): estado
``NO VERIFICADO`` hasta la FASE 22. Toda llamada al sistema esta aislada en
``MacLaunchBoundary`` para que los tests de contrato en Windows la sustituyan
por una frontera sintetica.

APIs y comandos usados (documentados por Apple; siempre con lista de
argumentos, nunca por shell):

* Descubrimiento puntual (sin recorrer el disco):
  - primer nivel de ``/Applications``, ``~/Applications`` y
    ``/System/Applications`` (``os.scandir``);
  - Spotlight: ``mdfind "kMDItemContentType == 'com.apple.application-bundle'
    && kMDItemDisplayName == '*<nombre>*'cd"`` y ``mdfind
    "kMDItemCFBundleIdentifier == '<bundle_id>'"``.
* Identidad: ``Contents/Info.plist`` con ``plistlib`` (CFBundleIdentifier,
  CFBundleName, CFBundleDisplayName, CFBundleExecutable). La identidad es el
  bundle id, nunca la ruta.
* Lanzamiento: ``open -b <bundle_id>`` (LaunchServices).
* Proceso: ``NSRunningApplication.runningApplicationsWithBundleIdentifier_``
  (AppKit via pyobjc, import perezoso) y, como alternativa, ``psutil`` por el
  ejecutable dentro del bundle.
* Gatekeeper/cuarentena: ``xattr -p com.apple.quarantine <bundle>`` y
  ``spctl --assess --type execute <bundle>``. Son motivos de bloqueo del
  preflight; nunca se eliminan atributos ni se elude la proteccion.
* Inventario: los bundles encontrados se registran en
  ``application_candidates`` de ``data/system_inventory.sqlite3`` por
  ``machine_id`` con los metodos existentes de ``SystemInventoryStorage``
  (ejecucion de escaneo parcial), sin escaneo completo.
"""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.core.log import get_logger
from src.core.operation_errors import ErrorCode, OperationError, OperationStage
from src.desktop.platform_contract import Capability, CapabilityReport, CapabilityStatus
from src.hands.apps.platform_launch import (
    AMBIGUOUS,
    NOT_FOUND,
    RESOLVED,
    TARGET_BUNDLE,
    TARGET_URL,
    ApplicationLaunchAdapter,
    LaunchOutcome,
    LaunchPreflight,
    LaunchTarget,
    ResolutionOutcome,
    find_entity_by_platform_identity,
    get_platform_identity,
    is_safe_launch_text,
)

logger = get_logger(__name__)

APPLICATION_ROOTS = ("/Applications", "~/Applications", "/System/Applications")
_SAFE_QUERY_TEXT = re.compile(r"^[A-Za-z0-9 ._+-]{1,80}$")
_SAFE_BUNDLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,254}$")
SUBPROCESS_TIMEOUT = 10.0


class MacLaunchBoundary:
    """Unica clase que toca el SO en macOS. Devuelve datos Python planos."""

    def __init__(self, timeout: float = SUBPROCESS_TIMEOUT) -> None:
        self.timeout = float(timeout)

    def _run(self, argv: Sequence[str]) -> subprocess.CompletedProcess:
        return subprocess.run(list(argv), capture_output=True, text=True, timeout=self.timeout, check=False)

    def list_application_bundles(self, roots: Sequence[str] = APPLICATION_ROOTS) -> List[str]:
        """Bundles .app del primer nivel de las carpetas de aplicaciones."""
        found: List[str] = []
        for root in roots:
            path = os.path.expanduser(root)
            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        if entry.name.endswith(".app") and entry.is_dir(follow_symlinks=False):
                            found.append(entry.path)
            except OSError as exc:
                logger.debug("No se pudo listar %s: %s", root, exc)
        return found

    def spotlight_by_name(self, name: str) -> List[str]:
        """``mdfind`` de bundles cuyo nombre visible contiene ``name``."""
        if not _SAFE_QUERY_TEXT.match(name or ""):
            return []
        query = (
            "kMDItemContentType == 'com.apple.application-bundle' && "
            "kMDItemDisplayName == '*%s*'cd" % name
        )
        try:
            result = self._run(["mdfind", query])
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("mdfind no disponible: %s", exc)
            return []
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip().endswith(".app")]

    def spotlight_by_bundle_id(self, bundle_id: str) -> List[str]:
        if not _SAFE_BUNDLE_ID.match(bundle_id or ""):
            return []
        try:
            result = self._run(["mdfind", "kMDItemCFBundleIdentifier == '%s'" % bundle_id])
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("mdfind no disponible: %s", exc)
            return []
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip().endswith(".app")]

    def read_info_plist(self, bundle_path: str) -> Dict[str, Any]:
        plist_path = os.path.join(bundle_path, "Contents", "Info.plist")
        try:
            with open(plist_path, "rb") as fh:
                data = plistlib.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, plistlib.InvalidFileException, ValueError) as exc:
            logger.debug("Info.plist ilegible: %s", exc)
            return {}

    def is_quarantined(self, bundle_path: str) -> Optional[bool]:
        """``xattr -p com.apple.quarantine``: True si existe el atributo."""
        try:
            result = self._run(["xattr", "-p", "com.apple.quarantine", bundle_path])
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("xattr no disponible: %s", exc)
            return None
        return result.returncode == 0 and bool((result.stdout or "").strip())

    def gatekeeper_assess(self, bundle_path: str) -> Optional[bool]:
        """``spctl --assess --type execute``: True aceptada, False rechazada, None sin dato."""
        try:
            result = self._run(["spctl", "--assess", "--type", "execute", bundle_path])
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("spctl no disponible: %s", exc)
            return None
        return result.returncode == 0

    def open_bundle(self, bundle_id: str) -> int:
        """``open -b <bundle_id>`` (LaunchServices). Devuelve el codigo de salida."""
        result = self._run(["open", "-b", bundle_id])
        return int(result.returncode)

    def running_pids(self, bundle_id: str, executable_path: Optional[str] = None) -> List[int]:
        """PIDs de la app por bundle id (NSRunningApplication) o por ejecutable (psutil)."""
        pids: List[int] = []
        if sys.platform == "darwin":
            try:
                from AppKit import NSRunningApplication  # type: ignore

                apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id) or []
                for app in apps:
                    pid = int(app.processIdentifier())
                    if pid > 0:
                        pids.append(pid)
            except Exception as exc:
                logger.debug("NSRunningApplication no disponible: %s", exc)
        if not pids and executable_path:
            try:
                import psutil

                for proc in psutil.process_iter(["pid", "exe"]):
                    if proc.info.get("exe") == executable_path:
                        pids.append(int(proc.info["pid"]))
            except Exception as exc:
                logger.debug("psutil no pudo listar procesos: %s", exc)
        return pids


_DEFAULT_BOUNDARY: Optional[MacLaunchBoundary] = None


def _boundary(boundary: Optional[MacLaunchBoundary]) -> MacLaunchBoundary:
    global _DEFAULT_BOUNDARY
    if boundary is not None:
        return boundary
    if _DEFAULT_BOUNDARY is None:
        _DEFAULT_BOUNDARY = MacLaunchBoundary()
    return _DEFAULT_BOUNDARY


def bundle_identity(bundle_path: str, boundary: Optional[MacLaunchBoundary] = None) -> Dict[str, str]:
    """Identidad de un bundle desde su Info.plist (sin rutas en el resultado salvo
    ``executable_path``, que es dato local privado)."""
    info = _boundary(boundary).read_info_plist(bundle_path)
    bundle_id = str(info.get("CFBundleIdentifier", "") or "")
    name = str(info.get("CFBundleDisplayName", "") or info.get("CFBundleName", "") or "")
    if not name:
        name = os.path.splitext(os.path.basename(bundle_path.rstrip("/")))[0]
    executable = str(info.get("CFBundleExecutable", "") or "")
    executable_path = os.path.join(bundle_path, "Contents", "MacOS", executable) if executable else ""
    return {
        "bundle_id": bundle_id,
        "bundle_name": name,
        "executable": executable,
        "executable_path": executable_path,
    }


def inspect_bundle_for_preflight(
    bundle: str,
    expected_bundle_id: Optional[str] = None,
    boundary: Optional[MacLaunchBoundary] = None,
) -> Dict[str, Any]:
    """Datos que necesita ``ApplicationPreflight`` para un bundle macOS.

    ``bundle`` es una ruta ``.app`` o un bundle id. Devuelve ``exists``,
    ``bundle_id``, ``identity_mismatch``, ``quarantined``, ``gatekeeper_ok`` y
    ``executable_path``. No modifica nada.
    """
    b = _boundary(boundary)
    path = str(bundle or "").strip()
    if not path.endswith(".app"):
        matches = b.spotlight_by_bundle_id(path)
        path = matches[0] if matches else ""
    if not path or not os.path.isdir(path):
        return {"exists": False}
    ident = bundle_identity(path, b)
    mismatch = bool(expected_bundle_id) and ident.get("bundle_id", "").casefold() != str(expected_bundle_id).casefold()
    return {
        "exists": True,
        "bundle_id": ident.get("bundle_id"),
        "identity_mismatch": mismatch,
        "quarantined": b.is_quarantined(path),
        "gatekeeper_ok": b.gatekeeper_assess(path),
        "executable_path": ident.get("executable_path") or None,
    }


def register_bundles_in_inventory(
    targets: Sequence[LaunchTarget],
    storage: Any = None,
    machine_id: Optional[str] = None,
) -> int:
    """Registra bundles descubiertos en ``application_candidates`` (mismo esquema).

    Usa una ejecucion de escaneo con resultado parcial sobre el volumen raiz:
    deja claro que no es un inventario completo. Aislado por ``machine_id``.
    """
    bundles = [t for t in targets if t.target_type == TARGET_BUNDLE and t.evidence.get("bundle_path")]
    if not bundles:
        return 0
    from src.hands.inventory.system_inventory import generate_machine_id
    from src.hands.inventory.system_inventory_storage import (
        SCAN_MODE_INCREMENTAL,
        SCAN_RESULT_PARTIAL,
        SystemInventoryStorage,
    )

    if storage is None:
        from src.core.config import get_project_root

        storage = SystemInventoryStorage(os.path.join(str(get_project_root()), "data", "system_inventory.sqlite3"))
    mid = machine_id or generate_machine_id()
    storage.initialize(machine_id_actual=mid)
    storage.record_machine(mid)
    scan_id = "puntual-macos-%s" % uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    storage.begin_scan_run(scan_id, mid, "/", SCAN_MODE_INCREMENTAL, started_at=now)
    inserted = 0
    try:
        rows = []
        for target in bundles:
            rows.append({
                "candidate_id": "bundle:%s:%s" % (mid, target.app_id or target.identity),
                "name": target.display_name,
                "absolute_path": target.evidence.get("bundle_path"),
                "launch_type": "bundle",
                "confidence": 1.0 if target.app_id else 0.5,
                "version": target.evidence.get("version"),
                "producto": target.app_id or None,
                "evidencia": ["bundle_id:%s" % target.app_id] if target.app_id else [],
                "source": target.source or "macos_bundles",
                "last_checked_at": now,
            })
        inserted = storage.insert_application_candidates(scan_id, mid, "/", rows)
        storage.end_scan_run(scan_id, result=SCAN_RESULT_PARTIAL, entries_count=inserted,
                             coverage_estimate="descubrimiento_puntual_bundles")
    except Exception:
        storage.end_scan_run(scan_id, result=SCAN_RESULT_PARTIAL, entries_count=inserted,
                             coverage_estimate="descubrimiento_puntual_fallido")
        raise
    return inserted


class MacOSLaunchAdapter(ApplicationLaunchAdapter):
    """Adaptador macOS del contrato de lanzamiento (NO VERIFICADO sin Mac)."""

    platform_name = "macos"

    def __init__(
        self,
        app_manager: Any = None,
        desktop: Any = None,
        boundary: Optional[MacLaunchBoundary] = None,
        preflight: Any = None,
        storage: Any = None,
        machine_id: Optional[str] = None,
        register_inventory: bool = True,
    ) -> None:
        super().__init__(desktop=desktop)
        self._app_manager = app_manager
        self.boundary = boundary or MacLaunchBoundary()
        self._preflight = preflight
        self._storage = storage
        self._machine_id = machine_id
        self.register_inventory = bool(register_inventory)

    @property
    def preflight_engine(self) -> Any:
        if self._preflight is None:
            from src.hands.apps.application_preflight import get_application_preflight

            self._preflight = get_application_preflight()
        return self._preflight

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        on_mac = sys.platform == "darwin"
        status = CapabilityStatus.NO_VERIFICADO if on_mac else CapabilityStatus.NO_SOPORTADO
        detail = "implementado sin verificar en Mac real" if on_mac else "adaptador macOS fuera de macOS"
        return {
            cap: CapabilityReport(cap, status, detail, backend=backend)
            for cap, backend in (
                (Capability.DISCOVER, "Applications+mdfind"),
                (Capability.RESOLVE, "Info.plist bundle id"),
                (Capability.PREFLIGHT, "ApplicationPreflight+Gatekeeper"),
                (Capability.LAUNCH, "open -b"),
                (Capability.PROCESS_VERIFY, "NSRunningApplication/psutil"),
                (Capability.WINDOW_VERIFY, "contrato_escritorio"),
            )
        }

    def _target_from_bundle(self, bundle_path: str, source: str) -> Optional[LaunchTarget]:
        ident = bundle_identity(bundle_path, self.boundary)
        bundle_id = ident.get("bundle_id", "")
        if not bundle_id or not _SAFE_BUNDLE_ID.match(bundle_id):
            return None
        executable = ident.get("executable", "")
        return LaunchTarget(
            identity="bundle:%s" % bundle_id,
            display_name=ident.get("bundle_name", "") or bundle_id,
            target_type=TARGET_BUNDLE,
            target=bundle_id,
            platform="macos",
            source=source,
            app_id=bundle_id,
            process_names=[executable] if executable else [],
            machine_id=self._machine_id,
            evidence={"bundle_path": bundle_path, "executable_path": ident.get("executable_path")},
        )

    def discover(self, name: str) -> List[LaunchTarget]:
        if not is_safe_launch_text(name):
            return []
        wanted = name.strip().casefold()
        paths: List[str] = []
        for path in self.boundary.list_application_bundles():
            if wanted in os.path.basename(path).casefold():
                paths.append(path)
        for path in self.boundary.spotlight_by_name(name.strip()):
            if path not in paths:
                paths.append(path)
        targets: Dict[str, LaunchTarget] = {}
        for path in paths:
            target = self._target_from_bundle(path, "macos_bundles")
            if target is not None:
                targets.setdefault(target.app_id.casefold(), target)
        return list(targets.values())

    def resolve(self, name: str) -> ResolutionOutcome:
        if not is_safe_launch_text(name):
            return ResolutionOutcome(NOT_FOUND, error=OperationError(
                OperationStage.RESOLUTION, ErrorCode.INVALID_ARGUMENT, "Nombre de aplicacion no admitido"))
        # 1) Identidad macOS enlazada en el catalogo global (bundle id, sin rutas).
        bundle_id = self._catalog_bundle_id(name)
        if bundle_id:
            for path in self.boundary.spotlight_by_bundle_id(bundle_id):
                target = self._target_from_bundle(path, "catalogo_global")
                if target is not None:
                    return ResolutionOutcome(RESOLVED, target, [target], None, "catalogo_global")
        # 2) Descubrimiento puntual por nombre.
        targets = self.discover(name)
        exact = [t for t in targets if t.display_name.casefold() == name.strip().casefold()]
        pool = exact or targets
        if self.register_inventory and targets:
            try:
                register_bundles_in_inventory(targets, self._storage, self._machine_id)
            except Exception as exc:
                logger.warning("No se pudieron registrar bundles en el inventario local: %s", exc)
        if len(pool) == 1:
            return ResolutionOutcome(RESOLVED, pool[0], pool, None, "macos_bundles")
        if len(pool) > 1:
            return ResolutionOutcome(AMBIGUOUS, None, pool, OperationError(
                OperationStage.RESOLUTION, ErrorCode.AMBIGUOUS, "varios bundles plausibles",
                needs_clarification=True, candidates=[t.display_name for t in pool]), "macos_bundles")
        return ResolutionOutcome(NOT_FOUND, error=OperationError(
            OperationStage.RESOLUTION, ErrorCode.NOT_INSTALLED,
            "Aplicacion no encontrada en este Mac: %s" % name), source="macos_bundles")

    def _catalog_bundle_id(self, name: str) -> str:
        try:
            manager = self._app_manager
            if manager is None:
                from src.hands.apps.applications_core import get_application_manager

                manager = get_application_manager()
            app = manager.get_application(name)
            entity_id = (getattr(app, "metadata", None) or {}).get("entity_id") if app else None
            if entity_id:
                entity = manager.memory_manager.get_entity(entity_id)
                ident = get_platform_identity(entity, "macos") if entity else {}
                return str(ident.get("bundle_id", "") or "")
            entity = find_entity_by_platform_identity("macos", "bundle_name", name)
            if entity is not None:
                return str(get_platform_identity(entity, "macos").get("bundle_id", "") or "")
        except Exception as exc:
            logger.debug("No se pudo leer la identidad macOS del catalogo: %s", exc)
        return ""

    def preflight(self, target: LaunchTarget) -> LaunchPreflight:
        application = {"name": target.display_name, "app_id": target.app_id, "bundle_id": target.app_id}
        destination = target.evidence.get("bundle_path") or target.target
        result = self.preflight_engine.check_launch_target(
            application, destination, target_type=target.target_type
        )
        return LaunchPreflight.from_preflight_dict(result)

    def launch(
        self,
        target: LaunchTarget,
        timeout: float = 15.0,
        spawner: Optional[Callable[[Sequence[str]], Any]] = None,
        url_opener: Optional[Callable[[str], bool]] = None,
    ) -> LaunchOutcome:
        if target.target_type != TARGET_BUNDLE:
            return super().launch(target, timeout=timeout, spawner=spawner, url_opener=url_opener)
        if not _SAFE_BUNDLE_ID.match(target.target or ""):
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.UNSAFE_ARGUMENT, "Bundle id no admitido"),
                target, target.display_name,
            )
        started = time.time()
        executable_path = target.evidence.get("executable_path")
        before = self.boundary.running_pids(target.target, executable_path)
        try:
            code = self.boundary.open_bundle(target.target)
        except subprocess.TimeoutExpired:
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.TIMEOUT, "open -b no respondio a tiempo",
                               retryable=False),
                target, target.display_name,
            )
        except OSError as exc:
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED, "Fallo al lanzar: %s" % exc),
                target, target.display_name,
            )
        if code != 0:
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED,
                               "LaunchServices no abrio la aplicacion (codigo %s)" % code),
                target, target.display_name,
            )
        pid = None
        deadline = time.monotonic() + min(5.0, max(0.5, float(timeout)))
        while time.monotonic() < deadline:
            pids = [p for p in self.boundary.running_pids(target.target, executable_path) if p not in before]
            if pids:
                pid = pids[0]
                break
            time.sleep(self.poll_interval)
        return LaunchOutcome(
            True, pid=pid, target=target, launched=True, app_name=target.display_name,
            evidence={"launch_started_at": started, "preexisting_pids": sorted(before), "mechanism": "open -b"},
        )

    def find_running(self, target: LaunchTarget) -> List[int]:
        if target.target_type == TARGET_BUNDLE:
            return self.boundary.running_pids(target.target, target.evidence.get("executable_path"))
        return super().find_running(target)


__all__ = [
    "MacLaunchBoundary",
    "MacOSLaunchAdapter",
    "bundle_identity",
    "inspect_bundle_for_preflight",
    "register_bundles_in_inventory",
    "APPLICATION_ROOTS",
]
