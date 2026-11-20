"""
Adaptador de descubrimiento y lanzamiento de aplicaciones para Windows.

Encapsula, sin cambiar su comportamiento, las fuentes y validaciones Windows
ya existentes y las expone con el contrato ``ApplicationLaunchAdapter``:

* Descubrimiento: ``ApplicationDiscovery`` (Menu Inicio/Get-StartApps, .lnk,
  AppX, registro de desinstaladores, PATH, App Paths e inventario SQLite).
* Resolucion local: primero el inventario por ``machine_id`` con
  revalidacion en el SO y auto-registro en el catalogo global
  (``resolver_aplicacion_por_nombre_con_desambiguacion``); si no hay destino
  local, las fuentes nativas (``buscar_por_nombre_con_desambiguacion`` sin
  inventario). Varios destinos plausibles -> ambiguedad, nunca eleccion
  silenciosa.
* Preflight: ``ApplicationPreflight.check_launch_target`` (politica comun +
  destino concreto + manifest).
* Lanzamiento (siempre argv estructurado o API del SO, nunca shell):
  ``exe``/``command`` -> proceso con argv de un elemento; ``lnk`` y URI
  admitida -> ``os.startfile``; ``aumid`` -> ``explorer.exe
  shell:AppsFolder\\<AUMID>`` como lista de argumentos; ``url`` -> navegador.
* Verificacion: proceso (psutil) y ventana visible por PID mediante el
  contrato de escritorio; para lanzadores de vida corta, procesos nuevos con el
  nombre esperado o ventanas nuevas aparecidas tras el lanzamiento.

No hace escaneos de disco completos: solo consultas puntuales a fuentes ya
permitidas y al inventario existente filtrado por ``machine_id``.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.core.log import get_logger
from src.core.operation_errors import ErrorCode, OperationError, OperationStage, redact_text
from src.desktop.platform_contract import Capability, CapabilityReport, CapabilityStatus
from src.hands.apps.aplicaciones_integradas_windows import (
    es_ruta_del_sistema_windows,
    ruta_windows_normalizada,
)
from src.hands.apps.platform_launch import (
    AMBIGUOUS,
    DEFAULT_ALLOWED_URI_SCHEMES,
    NOT_FOUND,
    RESOLVED,
    TARGET_AUMID,
    TARGET_COMMAND,
    TARGET_EXE,
    TARGET_LNK,
    TARGET_URI,
    TARGET_URL,
    ApplicationLaunchAdapter,
    LaunchOutcome,
    LaunchPreflight,
    LaunchTarget,
    ResolutionOutcome,
    is_safe_launch_text,
    uri_scheme,
)

logger = get_logger(__name__)

# Tipo de lanzamiento del clasificador (LaunchType) -> tipo de destino del contrato.
_LAUNCH_TYPE_TO_TARGET = {
    "ejecutable": TARGET_EXE,
    "acceso_directo": TARGET_LNK,
    "uri_aplicacion": TARGET_URI,
    "paquete": TARGET_AUMID,
}

_APPS_FOLDER_PREFIX = "shell:appsfolder\\"


_ruta_windows_normalizada = ruta_windows_normalizada


def _es_copia_del_sistema_o_del_paquete(target: Any, system_root: Optional[str] = None) -> bool:
    """True si el destino es un ejecutable del propio Windows o de un paquete.

    Cubre los ``.exe`` que Windows instala como alias o copias de una
    aplicacion empaquetada: los de ``%SystemRoot%`` (``System32\\calc.exe``,
    ``System32\\notepad.exe``) y los de ``\\WindowsApps\\`` (alias de
    ejecucion y copias del paquete). Un ``.exe`` instalado por el usuario en
    otra carpeta no lo es.
    """
    if getattr(target, "target_type", None) not in (TARGET_EXE, TARGET_COMMAND):
        return False
    ruta = _ruta_windows_normalizada(getattr(target, "target", ""))
    if not ruta:
        return False
    if "\\windowsapps\\" in ruta:
        return True
    return es_ruta_del_sistema_windows(ruta, system_root)


def _es_de_windowsapps(target: Any) -> bool:
    return "\\windowsapps\\" in _ruta_windows_normalizada(getattr(target, "target", ""))


def _nombre_ejecutable(target: Any) -> str:
    import ntpath

    nombre = ntpath.basename(_ruta_windows_normalizada(getattr(target, "target", "")))
    # Un destino `command` ("notepad") y un `exe` ("...\\notepad.exe") son el
    # mismo programa.
    return nombre[:-4] if nombre.endswith(".exe") else nombre


def preferir_destino_de_la_misma_aplicacion(
    targets: Sequence[Any], system_root: Optional[str] = None
) -> Optional[Any]:
    """Elige destino solo cuando todos son la MISMA aplicacion del sistema.

    No es un desempate general: si hay dos aplicaciones distintas que
    coinciden con el nombre pedido, devuelve None y el llamador declara
    ambiguedad (el usuario decide). Solo dos casos, ambos con una aplicacion
    del propio Windows que el SO expone por varias vias:

    1. Exactamente un paquete (AUMID) y el resto son ``.exe`` de
       ``%SystemRoot%`` o de ``WindowsApps`` (``System32\\calc.exe`` es un
       stub que abre la misma Calculadora empaquetada): se usa el AUMID.
    2. Sin paquetes, exactamente un ``.exe`` fuera de ``WindowsApps`` y el
       resto son copias en ``WindowsApps`` con el MISMO nombre de fichero
       (``System32\\notepad.exe`` frente a ``WindowsApps\\...\\notepad.exe``):
       se usa el de fuera de ``WindowsApps``, que es la ruta de produccion.
    """
    if len(targets) < 2:
        return None
    paquetes = [t for t in targets if getattr(t, "target_type", None) == TARGET_AUMID]
    resto = [t for t in targets if getattr(t, "target_type", None) != TARGET_AUMID]
    if len(paquetes) == 1:
        if all(_es_copia_del_sistema_o_del_paquete(t, system_root) for t in resto):
            return paquetes[0]
        return None
    if paquetes:
        return None
    if any(getattr(t, "target_type", None) not in (TARGET_EXE, TARGET_COMMAND) for t in targets):
        return None
    fuera = [t for t in targets if not _es_de_windowsapps(t)]
    if len(fuera) != 1:
        return None
    nombre = _nombre_ejecutable(fuera[0])
    if not nombre:
        return None
    copias = [t for t in targets if t is not fuera[0]]
    if all(_nombre_ejecutable(t) == nombre for t in copias):
        return fuera[0]
    return None


def _aumid_from_candidate(candidate: Any) -> str:
    """AUMID aportado por la fuente de descubrimiento (nunca inferido del nombre)."""
    for item in list(getattr(candidate, "evidencia", None) or []):
        if isinstance(item, str) and item.startswith("paquete_id:"):
            return item[len("paquete_id:"):].strip()
    for value in (getattr(candidate, "destination", None), getattr(candidate, "destino_original", None)):
        text = str(value or "").strip()
        if text.casefold().startswith(_APPS_FOLDER_PREFIX):
            return text[len(_APPS_FOLDER_PREFIX):].strip()
    return ""


def _infer_target_type(destination: str, launch_type: str) -> Optional[str]:
    mapped = _LAUNCH_TYPE_TO_TARGET.get(str(launch_type or "").strip().lower())
    if mapped:
        return mapped
    text = str(destination or "").strip()
    lower = text.casefold()
    if lower.endswith(".exe"):
        return TARGET_EXE
    if lower.endswith(".lnk"):
        return TARGET_LNK
    if lower.startswith(_APPS_FOLDER_PREFIX):
        return TARGET_AUMID
    scheme = uri_scheme(text)
    if scheme in ("http", "https"):
        return TARGET_URL
    if scheme:
        return TARGET_URI
    return None


# ---------------------------------------------------------------------------
# Identidad de paquete (AUMID) de las ventanas, sin depender del idioma
# ---------------------------------------------------------------------------

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_SUCCESS = 0
_ERROR_INSUFFICIENT_BUFFER = 122


def aumid_de_proceso(pid: int) -> Optional[str]:
    """AUMID del proceso ``pid`` (``GetApplicationUserModelId``, Windows 8+).

    None si no es Windows, el proceso no tiene identidad de aplicacion
    empaquetada (APPMODEL_ERROR_NO_APPLICATION: aplicacion de escritorio
    clasica) o no se puede abrir con PROCESS_QUERY_LIMITED_INFORMATION.
    """
    if sys.platform != "win32" or not pid:
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    funcion = getattr(kernel32, "GetApplicationUserModelId", None)
    if funcion is None:
        return None
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    funcion.restype = ctypes.c_long
    funcion.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_uint32), wintypes.LPWSTR]
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        longitud = ctypes.c_uint32(0)
        codigo = funcion(handle, ctypes.byref(longitud), None)
        if codigo != _ERROR_INSUFFICIENT_BUFFER or longitud.value == 0:
            return None
        bufer = ctypes.create_unicode_buffer(int(longitud.value))
        codigo = funcion(handle, ctypes.byref(longitud), bufer)
        if codigo != _ERROR_SUCCESS:
            return None
        return bufer.value or None
    finally:
        kernel32.CloseHandle(handle)


def pids_de_ventanas_hijas(hwnd: int) -> List[int]:
    """PIDs de las ventanas hijas de ``hwnd`` distintos del propio.

    Las aplicaciones UWP se muestran dentro de una ventana de
    ApplicationFrameHost.exe; la aplicacion real es el proceso de una ventana
    hija (``Windows.UI.Core.CoreWindow``).
    """
    if sys.platform != "win32" or not hwnd:
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    propio = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(wintypes.HWND(int(hwnd)), ctypes.byref(propio))
    encontrados: List[int] = []
    tipo_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _visitar(hijo: Any, _param: Any) -> bool:
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hijo, ctypes.byref(pid))
        if pid.value and pid.value != propio.value and pid.value not in encontrados:
            encontrados.append(int(pid.value))
        return True

    callback = tipo_callback(_visitar)
    user32.EnumChildWindows.restype = wintypes.BOOL
    user32.EnumChildWindows.argtypes = [wintypes.HWND, tipo_callback, wintypes.LPARAM]
    user32.EnumChildWindows(wintypes.HWND(int(hwnd)), callback, 0)
    return encontrados


def aumids_de_ventana_windows(window: Any) -> List[str]:
    """AUMID del proceso de la ventana y de los procesos de sus hijas."""
    resultado: List[str] = []
    pids = [int(getattr(window, "pid", 0) or 0)] + pids_de_ventanas_hijas(int(window.window_id))
    for pid in pids:
        aumid = aumid_de_proceso(pid)
        if aumid and aumid not in resultado:
            resultado.append(aumid)
    return resultado


class WindowsLaunchAdapter(ApplicationLaunchAdapter):
    """Adaptador Windows del contrato de lanzamiento."""

    platform_name = "windows"

    def __init__(
        self,
        app_manager: Any = None,
        desktop: Any = None,
        discovery: Any = None,
        preflight: Any = None,
        startfile: Optional[Callable[[str], Any]] = None,
        allowed_uri_schemes: Optional[Sequence[str]] = None,
        machine_id: Optional[str] = None,
        aumids_de_ventana: Optional[Callable[[Any], Sequence[str]]] = None,
    ) -> None:
        super().__init__(desktop=desktop)
        self._app_manager = app_manager
        # Lectura de los AUMID de los procesos de una ventana; inyectable para
        # probar la verificacion sin APIs de Windows.
        self._aumids_de_ventana = aumids_de_ventana or aumids_de_ventana_windows
        self._discovery = discovery
        self._preflight = preflight
        self._startfile = startfile
        self.allowed_uri_schemes = frozenset(
            s.lower() for s in (allowed_uri_schemes or DEFAULT_ALLOWED_URI_SCHEMES)
        )
        self._machine_id = machine_id

    # ------------------------------------------------------------------
    # Dependencias perezosas
    # ------------------------------------------------------------------

    @property
    def preflight_engine(self) -> Any:
        if self._preflight is None:
            from src.hands.apps.application_preflight import get_application_preflight

            self._preflight = get_application_preflight()
        return self._preflight

    @property
    def discovery(self) -> Any:
        """``ApplicationDiscovery`` con la base del inventario en la ruta absoluta
        del proyecto (la misma que usa el preflight)."""
        if self._discovery is None:
            from src.core.config import get_project_root
            from src.hands.apps.application_discovery import ApplicationDiscovery
            from src.hands.inventory.system_inventory_storage import SystemInventoryStorage

            db_path = os.path.join(str(get_project_root()), "data", "system_inventory.sqlite3")
            self._discovery = ApplicationDiscovery(
                preflight=self.preflight_engine,
                storage=SystemInventoryStorage(db_path),
                machine_id=self._machine_id,
                app_manager=self._app_manager,
            )
        return self._discovery

    @property
    def machine_id(self) -> Optional[str]:
        if self._machine_id:
            return self._machine_id
        try:
            return str(getattr(self.discovery, "machine_id", None) or "") or None
        except Exception as exc:
            logger.debug("machine_id no disponible: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Capacidades
    # ------------------------------------------------------------------

    def capabilities(self) -> Dict[Capability, CapabilityReport]:
        on_windows = sys.platform == "win32"
        base = CapabilityStatus.DISPONIBLE if on_windows else CapabilityStatus.NO_SOPORTADO
        detail = "" if on_windows else "adaptador Windows fuera de Windows"
        reports = {
            Capability.DISCOVER: CapabilityReport(Capability.DISCOVER, base, detail, backend="ApplicationDiscovery"),
            Capability.RESOLVE: CapabilityReport(Capability.RESOLVE, base, detail, backend="inventario_sqlite+fuentes_nativas"),
            Capability.PREFLIGHT: CapabilityReport(Capability.PREFLIGHT, base, detail, backend="ApplicationPreflight"),
            Capability.LAUNCH: CapabilityReport(Capability.LAUNCH, base, detail, backend="argv/os.startfile/shell:AppsFolder"),
        }
        try:
            import psutil  # noqa: F401

            proc_status = base
        except Exception:
            proc_status = CapabilityStatus.NO_SOPORTADO
        reports[Capability.PROCESS_VERIFY] = CapabilityReport(Capability.PROCESS_VERIFY, proc_status, backend="psutil")
        window_status = CapabilityStatus.NO_VERIFICADO
        desktop = self._get_desktop() if on_windows else None
        if desktop is not None:
            try:
                window_status = desktop.capability_status(Capability.WINDOW_VERIFY)
            except Exception as exc:
                logger.debug("capability_status(WINDOW_VERIFY) fallo: %s", exc)
        elif not on_windows:
            window_status = CapabilityStatus.NO_SOPORTADO
        reports[Capability.WINDOW_VERIFY] = CapabilityReport(Capability.WINDOW_VERIFY, window_status, backend="contrato_escritorio")
        return reports

    # ------------------------------------------------------------------
    # Descubrimiento y resolucion
    # ------------------------------------------------------------------

    def _candidate_to_target(self, candidate: Any) -> Optional[LaunchTarget]:
        if not getattr(candidate, "disponible", True):
            return None
        if getattr(candidate, "es_lanzable", True) is False:
            return None
        decision = getattr(candidate, "preflight_decision", None)
        if isinstance(decision, dict) and decision.get("valid") is False:
            return None
        destination = str(getattr(candidate, "destination", None) or getattr(candidate, "absolute_path", None) or "").strip()
        launch_type = str(getattr(candidate, "launch_type", "") or "")
        aumid = _aumid_from_candidate(candidate) or str(getattr(candidate, "app_id", None) or "").strip()
        target_type = TARGET_AUMID if (aumid and launch_type == "paquete") else _infer_target_type(destination, launch_type)
        if target_type is None:
            return None
        target_value = aumid if target_type == TARGET_AUMID else destination
        if not target_value:
            return None
        process_names: List[str] = []
        if target_type == TARGET_EXE:
            process_names = [os.path.basename(destination.replace("\\", "/"))]
        elif target_type == TARGET_LNK:
            try:
                from src.hands.apps.application_launch_classifier import resolver_target_acceso_directo

                resolved = resolver_target_acceso_directo(destination)
                if resolved:
                    process_names = [os.path.basename(resolved.replace("\\", "/"))]
            except Exception as exc:
                logger.debug("No se pudo resolver el destino del .lnk: %s", exc)
        identity = ""
        try:
            from src.hands.apps.application_discovery import calcular_identidad_estable

            identity = calcular_identidad_estable(candidate).entity_id
        except Exception as exc:
            logger.debug("No se pudo calcular la identidad estable: %s", exc)
        name = str(getattr(candidate, "nombre_comercial", None) or getattr(candidate, "name", "") or "")
        return LaunchTarget(
            identity=identity or "candidato:%s" % getattr(candidate, "candidate_id", name),
            display_name=name,
            target_type=target_type,
            target=target_value,
            platform="windows",
            source=str(getattr(candidate, "fuente", "") or ""),
            app_id=aumid,
            process_names=process_names,
            machine_id=self._machine_id,
            evidence={
                "fuente": getattr(candidate, "fuente", ""),
                "confianza": getattr(candidate, "confianza", ""),
                "launch_type": launch_type,
                "launch_subtype": getattr(candidate, "launch_subtype", ""),
                "preflight_destino": decision,
            },
        )

    def _new_window_by_app_id(
        self, desktop: Any, before: Sequence[int], app_id: str
    ) -> Optional[Any]:
        """Ventana nueva cuyo proceso (o el proceso de la app alojada en
        ApplicationFrameHost) tiene exactamente el AUMID ``app_id``."""
        buscado = str(app_id or "").strip().casefold()
        if desktop is None or not buscado or "!" not in buscado:
            return None
        known = set(int(w) for w in before)
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
            try:
                aumids = self._aumids_de_ventana(window) or ()
            except Exception as exc:
                logger.debug("No se pudo leer el AUMID de la ventana %s: %s", window.window_id, exc)
                continue
            if any(str(a).strip().casefold() == buscado for a in aumids):
                return window
        return None

    def discover(self, name: str) -> List[LaunchTarget]:
        """Busqueda puntual por nombre en las fuentes permitidas (sin lanzar)."""
        if not is_safe_launch_text(name):
            return []
        try:
            candidates = self.discovery.buscar_por_nombre(name)
        except Exception as exc:
            logger.warning("Descubrimiento por nombre fallo: %s", exc)
            return []
        targets = []
        for candidate in candidates or []:
            target = self._candidate_to_target(candidate)
            if target is not None:
                targets.append(target)
        return targets

    def _from_resolution(self, resolution: Any, source: str) -> ResolutionOutcome:
        alternatives = list(getattr(resolution, "alternativas", None) or [])
        candidates = list(getattr(resolution, "candidatos", None) or [])
        if getattr(resolution, "requiere_desambiguacion", False) or getattr(resolution, "ambiguo", False):
            pool = alternatives or candidates
            targets = [t for t in (self._candidate_to_target(c) for c in pool) if t is not None]
            return ResolutionOutcome(AMBIGUOUS, None, targets, OperationError(
                OperationStage.RESOLUTION, ErrorCode.AMBIGUOUS,
                str(getattr(resolution, "motivo_ambiguedad", "") or "varios destinos plausibles"),
                needs_clarification=True,
                candidates=[t.display_name for t in targets],
            ), source)
        targets = [t for t in (self._candidate_to_target(c) for c in candidates) if t is not None]
        # Deduplicar por destino real conservando el destino de mayor precedencia.
        unicos = {}
        for target in targets:
            clave = (target.target_type, target.target.casefold())
            if clave not in unicos:
                unicos[clave] = target
        targets = list(unicos.values())
        if len(targets) > 1:
            preferido = preferir_destino_de_la_misma_aplicacion(targets)
            if preferido is not None:
                return ResolutionOutcome(RESOLVED, preferido, targets, None, source)
        if len(targets) == 1:
            return ResolutionOutcome(RESOLVED, targets[0], targets, None, source)
        if len(targets) > 1:
            return ResolutionOutcome(AMBIGUOUS, None, targets, OperationError(
                OperationStage.RESOLUTION, ErrorCode.AMBIGUOUS,
                "varios destinos locales plausibles", needs_clarification=True,
                candidates=[t.display_name for t in targets],
            ), source)
        return ResolutionOutcome(NOT_FOUND, None, [], None, source)

    def resolve(self, name: str) -> ResolutionOutcome:
        """Resolucion local por ``machine_id`` y, si no hay destino, fuentes nativas."""
        if not is_safe_launch_text(name):
            return ResolutionOutcome(NOT_FOUND, error=OperationError(
                OperationStage.RESOLUTION, ErrorCode.INVALID_ARGUMENT, "Nombre de aplicacion no admitido"))
        if sys.platform != "win32":
            return ResolutionOutcome(NOT_FOUND, error=OperationError(
                OperationStage.RESOLUTION, ErrorCode.ADAPTER_MISSING,
                "El adaptador Windows no puede resolver en %s" % sys.platform))
        discovery = self.discovery
        # 1) Inventario local por machine_id + revalidacion + auto-registro.
        try:
            local = discovery.resolver_aplicacion_por_nombre_con_desambiguacion(name, incluir_preflight=True)
            outcome = self._from_resolution(local, "inventario_local")
            if outcome.status in (RESOLVED, AMBIGUOUS):
                return outcome
        except Exception as exc:
            logger.warning("Resolucion en inventario local fallo: %s", exc)
        # 2) Fuentes nativas del SO (Menu Inicio, AppX, registro, PATH, App Paths).
        try:
            native = discovery.buscar_por_nombre_con_desambiguacion(name, incluir_inventario=False)
            outcome = self._from_resolution(native, "fuentes_nativas")
            if outcome.status == RESOLVED and outcome.target is not None:
                self._auto_register(native, outcome.target)
            return outcome if outcome.status != NOT_FOUND else ResolutionOutcome(
                NOT_FOUND, error=OperationError(
                    OperationStage.RESOLUTION, ErrorCode.NOT_INSTALLED,
                    "Aplicacion no encontrada en este equipo: %s" % name),
                source="fuentes_nativas")
        except Exception as exc:
            logger.warning("Resolucion en fuentes nativas fallo: %s", exc)
            return ResolutionOutcome("error", error=OperationError(
                OperationStage.RESOLUTION, ErrorCode.INTERNAL,
                "Fallo consultando las fuentes de descubrimiento: %s" % exc, retryable=True))

    def _auto_register(self, resolution: Any, target: LaunchTarget) -> None:
        """Auto-registro idempotente en el catalogo global del candidato elegido.

        Reutiliza las funciones del descubrimiento (identidad estable, registro
        minimo y fusion con la entidad existente). No guarda la ruta como
        verdad: el registro minimo solo la conserva como observacion.
        """
        try:
            from src.hands.apps.application_discovery import (
                _fusionar_entidad_existente,
                calcular_identidad_estable,
                construir_registro_minimo_aplicacion,
                validar_registro_minimo_aplicacion,
            )
            from src.memory.storage import Entity

            candidates = list(getattr(resolution, "candidatos", None) or [])
            chosen = None
            for candidate in candidates:
                mapped = self._candidate_to_target(candidate)
                if mapped is not None and mapped.target == target.target:
                    chosen = candidate
                    break
            if chosen is None:
                return
            identity = calcular_identidad_estable(chosen)
            registro = construir_registro_minimo_aplicacion(chosen, identity)
            if validar_registro_minimo_aplicacion(registro):
                return
            memory_manager = self.discovery.app_manager.memory_manager
            nueva = Entity.from_dict(registro.a_dict_entidad())
            existente = memory_manager.get_entity(nueva.id)
            if existente is not None:
                nueva = Entity.from_dict(_fusionar_entidad_existente(existente.to_dict(), nueva.to_dict()))
            memory_manager.save_entity(nueva)
            target.catalog_entity_id = nueva.id
        except Exception as exc:
            logger.warning("Auto-registro del candidato descubierto fallo: %s", exc)

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------

    def preflight(self, target: LaunchTarget) -> LaunchPreflight:
        if target.target_type == TARGET_URI:
            scheme = uri_scheme(target.target)
            if scheme not in self.allowed_uri_schemes:
                return LaunchPreflight(False, "Esquema URI no admitido: %s" % scheme, "unsupported_uri")
        application = {
            "name": target.display_name,
            "app_id": target.app_id,
            "url": target.target if target.target_type == TARGET_URL else None,
        }
        engine = self.preflight_engine
        checker = getattr(engine, "check_launch_target", None)
        if checker is None:
            return LaunchPreflight(False, "ApplicationPreflight sin check_launch_target", "preflight_unavailable")
        result = checker(application, target.target, target_type=target.target_type)
        return LaunchPreflight.from_preflight_dict(result)

    # ------------------------------------------------------------------
    # Lanzamiento
    # ------------------------------------------------------------------

    def _snapshot_window_ids(self) -> List[int]:
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

    def launch(
        self,
        target: LaunchTarget,
        timeout: float = 15.0,
        spawner: Optional[Callable[[Sequence[str]], Any]] = None,
        url_opener: Optional[Callable[[str], bool]] = None,
    ) -> LaunchOutcome:
        if target.target_type in (TARGET_EXE, TARGET_COMMAND, TARGET_URL):
            return super().launch(target, timeout=timeout, spawner=spawner, url_opener=url_opener)
        if sys.platform != "win32":
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.ADAPTER_MISSING,
                               "El adaptador Windows no lanza destinos en %s" % sys.platform),
                target, target.display_name,
            )
        started = time.time()
        preexisting = sorted(self._pids_by_names(target.process_names))
        windows_before = self._snapshot_window_ids()
        evidence = {
            "launch_started_at": started,
            "preexisting_pids": preexisting,
            "preexisting_window_ids": windows_before,
        }
        try:
            if target.target_type == TARGET_LNK:
                if not target.target.casefold().endswith(".lnk") or not os.path.isfile(target.target):
                    return LaunchOutcome.failed(
                        OperationError(OperationStage.LAUNCH, ErrorCode.TARGET_NOT_LOCALIZABLE,
                                       "El acceso directo ya no existe en este equipo"),
                        target, target.display_name,
                    )
                (self._startfile or os.startfile)(target.target)  # type: ignore[attr-defined]
                evidence["mechanism"] = "os.startfile(lnk)"
                return LaunchOutcome(True, target=target, launched=True, app_name=target.display_name, evidence=evidence)
            if target.target_type == TARGET_URI:
                scheme = uri_scheme(target.target)
                if scheme not in self.allowed_uri_schemes or not is_safe_launch_text(target.target):
                    return LaunchOutcome.failed(
                        OperationError(OperationStage.LAUNCH, ErrorCode.UNSUPPORTED_URI,
                                       "URI no admitida como lanzamiento: %s" % scheme),
                        target, target.display_name,
                    )
                (self._startfile or os.startfile)(target.target)  # type: ignore[attr-defined]
                evidence["mechanism"] = "os.startfile(uri)"
                return LaunchOutcome(True, target=target, launched=True, app_name=target.display_name, evidence=evidence)
            if target.target_type == TARGET_AUMID:
                aumid = target.target
                if not is_safe_launch_text(aumid) or "\\" in aumid or "/" in aumid:
                    return LaunchOutcome.failed(
                        OperationError(OperationStage.LAUNCH, ErrorCode.UNSAFE_ARGUMENT,
                                       "Identificador de paquete con caracteres no admitidos"),
                        target, target.display_name,
                    )
                spawn = spawner
                if spawn is None:
                    from src.hands.apps.platform_launch import _default_spawner

                    spawn = _default_spawner
                # Mismo mecanismo que CalibrationManager.launch_application.
                spawn(["explorer.exe", "shell:AppsFolder\\%s" % aumid])
                evidence["mechanism"] = "explorer shell:AppsFolder"
                return LaunchOutcome(True, target=target, launched=True, app_name=target.display_name, evidence=evidence)
        except FileNotFoundError as exc:
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.TARGET_NOT_LOCALIZABLE,
                               "El SO no encontro el destino: %s" % exc),
                target, target.display_name,
            )
        except PermissionError as exc:
            return LaunchOutcome.failed(
                OperationError(OperationStage.PERMISSION, ErrorCode.PERMISSION_DENIED,
                               "Permiso denegado al lanzar: %s" % exc),
                target, target.display_name,
            )
        except OSError as exc:
            return LaunchOutcome.failed(
                OperationError(OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED,
                               "Fallo al lanzar %s: %s" % (target.display_name, redact_text(str(exc)))),
                target, target.display_name,
            )
        return super().launch(target, timeout=timeout, spawner=spawner, url_opener=url_opener)


__all__ = ["WindowsLaunchAdapter"]
