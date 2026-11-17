"""
Vigencia, invalidacion y recalculo de perfiles de calibracion UI.

Cubre (referencia de localizacion en el roadmap): 3.8.6.9.1 - 3.8.6.9.4.

Reglas que aplica ``evaluate_profile_validity``:

* Otro ``machine_id`` u otro SO: ``reject``. Nunca se aplican perfiles de otro
  equipo (el almacen ademas filtra por ``machine_id``).
* Perfil no VALIDADO, datos incompletos o version de detector distinta:
  ``recalibrate`` y el perfil (o los controles afectados) se marcan OBSOLETO;
  nunca se reutilizan coordenadas antiguas en silencio.
* Transformacion no verificable en el entorno actual (sin area cliente, sin
  escala, ventana minimizada/oculta): no se usa el perfil (``reject`` para la
  accion actual) y no se marca obsoleto: el problema es del entorno.
* Cambio de escala/DPI, tamano del area cliente, estado de ventana, layout
  (huella del arbol de accesibilidad) o, en el mismo monitor, resolucion u
  orientacion: ``recalibrate`` de lo afectado.
* Misma escala y mismo tamano de area cliente en OTRO monitor, cambio de
  topologia o ventana desplazada: ``recompute`` (las coordenadas absolutas se
  recalculan desde la geometria relativa del area cliente, sin recalibrar).
* Todo coincide: ``use``.

Las coordenadas absolutas resultantes son una cache invalidable del perfil
(``absolute_cache``) y se expresan en el espacio de escritorio del adaptador
(``DESKTOP_PIXELS`` en Windows, ``DESKTOP_POINTS`` en macOS). El catalogo
global solo recibe ``calibration_required``; nunca coordenadas.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.desktop.platform_contract import (
    DESKTOP_PIXELS,
    DisplayInfo,
    Rect,
    WindowInfo,
)
from src.hands.calibration.calibration_profile_storage import (
    CalibratedControlRecord,
    CalibrationProfile,
    CalibrationProfileStore,
    CalibrationState,
    _valid_normalized_box,
)

logger = get_logger(__name__)

# Tolerancias de comparacion (unidades del SO; no son umbrales de deteccion).
SCALE_TOLERANCE = 1e-3
CLIENT_SIZE_TOLERANCE = 1  # redondeo de una unidad entre lecturas del SO

ACTION_USE = "use"
ACTION_RECOMPUTE = "recompute"
ACTION_RECALIBRATE = "recalibrate"
ACTION_REJECT = "reject"


class CalibrationEnvironmentError(ValueError):
    """No se pudo leer el entorno actual (ventana/monitor) desde el contrato."""


class CalibrationTransformError(ValueError):
    """Falta informacion para transformar geometria relativa a absoluta."""


# ============================================================================
# HUELLA DEL ENTORNO
# ============================================================================


def fallback_topology_fingerprint(displays: Iterable[DisplayInfo]) -> str:
    """Huella de topologia independiente del orden de enumeracion.

    Solo se usa si ``src.desktop.monitor_topology`` no esta disponible. Una
    diferencia de topologia por si sola solo provoca ``recompute``.
    """
    items = []
    for d in displays:
        items.append(
            "%s|%s|%dx%d|%.3f|%d|%d" % (
                d.display_id,
                d.bounds.to_int_tuple(),
                int(d.pixel_width),
                int(d.pixel_height),
                float(d.scale_factor or 1.0),
                int(d.rotation or 0),
                int(bool(d.is_primary)),
            )
        )
    return hashlib.sha256("\n".join(sorted(items)).encode("utf-8")).hexdigest()


def _topology_fingerprint(displays: List[DisplayInfo], topology: Any = None) -> str:
    if topology is not None and getattr(topology, "fingerprint", None):
        return str(topology.fingerprint)
    try:
        from src.desktop.monitor_topology import MonitorTopology

        return str(MonitorTopology.from_displays(displays).fingerprint)
    except Exception as exc:  # modulo ausente o error de construccion
        logger.debug("Huella de topologia de respaldo: %s", exc)
        return fallback_topology_fingerprint(displays)


def _display_for_window(window: WindowInfo, displays: Sequence[DisplayInfo]) -> Optional[DisplayInfo]:
    if window.display_id:
        for d in displays:
            if d.display_id == window.display_id:
                return d
    rect = window.client_bounds or window.frame_bounds or window.bounds
    if rect is None:
        return None
    best = None
    best_area = 0.0
    for d in displays:
        area = d.bounds.intersection_area(rect)
        if area > best_area:
            best, best_area = d, area
    if best is None:
        cx, cy = rect.center
        for d in displays:
            if d.bounds.contains_point(cx, cy):
                return d
    return best


def _window_state(window: WindowInfo) -> str:
    if window.is_minimized:
        return "minimized"
    if not window.is_visible:
        return "hidden"
    if window.is_maximized:
        return "maximized"
    return "normal"


@dataclass
class EnvironmentFingerprint:
    """Entorno actual de una ventana: equipo, monitor, escala, ventana y topologia.

    ``client_bounds``, ``window_id`` y ``display_bounds`` son datos de ejecucion
    (no forman parte de la huella persistida). ``layout_hash`` es opcional
    (huella del arbol de accesibilidad) para detectar cambios de tema, zoom
    interno o layout que no alteran el tamano.
    """

    machine_id: str
    platform: str
    display_id: str
    scale_factor: Optional[float]
    dpi: Optional[int]
    display_pixel_size: Optional[Tuple[int, int]]
    orientation: str
    window_state: str
    client_size: Optional[Tuple[int, int]]
    topology_fingerprint: str
    layout_hash: Optional[str] = None
    client_bounds: Optional[Rect] = None
    window_id: Optional[int] = None
    coordinate_space: str = DESKTOP_PIXELS
    detector_versions: Dict[str, str] = field(default_factory=dict)

    def window_fingerprint(self) -> str:
        """Huella de ventana/escala usada como parte de la clave de calibracion.

        Incluye equipo, SO, escala/DPI, tamano del area cliente y estado de
        ventana. No incluye el monitor ni la posicion: mover la ventana a otro
        monitor con la misma escala y tamano conserva la huella (``recompute``).
        """
        scale = "%.3f" % float(self.scale_factor) if self.scale_factor is not None else "none"
        size = "%dx%d" % tuple(self.client_size) if self.client_size else "none"
        raw = "|".join([
            str(self.machine_id),
            str(self.platform),
            scale,
            str(self.dpi if self.dpi is not None else "none"),
            size,
            str(self.window_state),
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_profile_fields(self) -> Dict[str, Any]:
        """Campos de ``CalibrationProfile`` derivados del entorno (para B6)."""
        return {
            "machine_id": self.machine_id,
            "platform": self.platform,
            "topology_fingerprint": self.topology_fingerprint,
            "window_fingerprint": self.window_fingerprint(),
            "display_id": self.display_id,
            "scale_factor": self.scale_factor,
            "dpi": self.dpi,
            "display_pixel_size": self.display_pixel_size,
            "orientation": self.orientation,
            "window_state": self.window_state,
            "client_size": self.client_size,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = self.to_profile_fields()
        data.update({
            "layout_hash": self.layout_hash,
            "client_bounds": self.client_bounds.to_dict() if self.client_bounds else None,
            "window_id": self.window_id,
            "coordinate_space": self.coordinate_space,
        })
        return data

    @classmethod
    def capture(
        cls,
        adapter: Any,
        window_id: int,
        machine_id: Optional[str] = None,
        topology: Any = None,
        layout_hash: Optional[str] = None,
    ) -> "EnvironmentFingerprint":
        """Lee el entorno real de la ventana mediante el contrato de plataforma.

        Levanta ``CalibrationEnvironmentError`` si la ventana o los monitores
        no se pueden leer (sin inventar valores).
        """
        if adapter is None:
            from src.desktop.platform_contract import get_desktop_platform

            adapter = get_desktop_platform()
        if machine_id is None:
            from src.hands.inventory.system_inventory import generate_machine_id

            machine_id = generate_machine_id()
        win_result = adapter.get_window(int(window_id))
        if not win_result.ok or win_result.value is None:
            raise CalibrationEnvironmentError(
                "No se pudo leer la ventana %s: %s" % (window_id, win_result.error)
            )
        window: WindowInfo = win_result.value
        if topology is not None and getattr(topology, "displays", None):
            displays = list(topology.displays)
        else:
            disp_result = adapter.enumerate_displays()
            if not disp_result.ok or not disp_result.value:
                raise CalibrationEnvironmentError(
                    "No se pudieron enumerar los monitores: %s" % disp_result.error
                )
            displays = list(disp_result.value)
        display = _display_for_window(window, displays)
        if display is None:
            raise CalibrationEnvironmentError("No se pudo determinar el monitor de la ventana %s" % window_id)

        scale = window.scale_factor
        dpi = window.dpi
        try:
            dpi_result = adapter.get_window_dpi_info(int(window_id))
            if dpi_result.ok and dpi_result.value is not None:
                if dpi_result.value.scale_factor is not None:
                    scale = dpi_result.value.scale_factor
                if dpi_result.value.dpi is not None:
                    dpi = dpi_result.value.dpi
        except Exception as exc:  # el contrato no debe levantar, pero se protege
            logger.debug("get_window_dpi_info(%s): %s", window_id, exc)
        if scale is None:
            scale = display.scale_factor
        if dpi is None:
            dpi = display.dpi

        client = window.client_bounds
        client_size = None
        if client is not None and client.is_valid():
            client_size = (int(round(client.width)), int(round(client.height)))

        return cls(
            machine_id=str(machine_id),
            platform=str(getattr(adapter, "platform_name", "") or ""),
            display_id=str(display.display_id),
            scale_factor=float(scale) if scale is not None else None,
            dpi=int(dpi) if dpi is not None else None,
            display_pixel_size=(int(display.pixel_width), int(display.pixel_height)),
            orientation=display.orientation,
            window_state=_window_state(window),
            client_size=client_size,
            topology_fingerprint=_topology_fingerprint(displays, topology),
            layout_hash=layout_hash,
            client_bounds=client if client is not None and client.is_valid() else None,
            window_id=int(window_id),
            coordinate_space=str(getattr(adapter, "desktop_space", DESKTOP_PIXELS) or DESKTOP_PIXELS),
        )


# ============================================================================
# EVALUACION DE VIGENCIA
# ============================================================================


@dataclass
class ProfileValidity:
    """Decision de vigencia de un perfil frente al entorno actual.

    ``valid`` es True solo si el perfil puede usarse ahora (``use`` o
    ``recompute``). ``usable_controls`` son los controles que pueden
    publicarse; ``affected_controls`` los que deben relocalizarse.
    ``mark_obsolete`` indica que el problema es del propio perfil (datos
    incompletos, detector distinto) y debe marcarse OBSOLETO.
    """

    valid: bool
    action: str
    changes: List[str] = field(default_factory=list)
    affected_controls: List[str] = field(default_factory=list)
    reason: str = ""
    usable_controls: List[str] = field(default_factory=list)
    mark_obsolete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "action": self.action,
            "changes": list(self.changes),
            "affected_controls": list(self.affected_controls),
            "usable_controls": list(self.usable_controls),
            "reason": self.reason,
            "mark_obsolete": self.mark_obsolete,
        }


def _all_ids(profile: CalibrationProfile) -> List[str]:
    return [c.control_id for c in profile.controls]


def _decision(
    action: str,
    profile: Optional[CalibrationProfile],
    changes: List[str],
    reason: str,
    affected: Optional[List[str]] = None,
    mark_obsolete: bool = False,
) -> ProfileValidity:
    ids = _all_ids(profile) if profile is not None else []
    if affected is None:
        affected = list(ids) if action in (ACTION_RECALIBRATE, ACTION_REJECT) else []
    valid = action in (ACTION_USE, ACTION_RECOMPUTE)
    usable = [cid for cid in ids if cid not in set(affected)] if valid else []
    return ProfileValidity(
        valid=valid,
        action=action,
        changes=list(changes),
        affected_controls=list(affected),
        reason=reason,
        usable_controls=usable,
        mark_obsolete=mark_obsolete,
    )


def evaluate_profile_validity(
    profile: Optional[CalibrationProfile],
    current: EnvironmentFingerprint,
    current_detector_versions: Optional[Dict[str, str]] = None,
) -> ProfileValidity:
    """Decide si un perfil puede usarse en el entorno actual (ver docstring del modulo)."""
    if profile is None:
        return _decision(ACTION_RECALIBRATE, None, ["sin_perfil"], "no hay perfil VALIDADO para la aplicacion")

    # 1. Equipo y SO.
    if profile.machine_id != current.machine_id:
        return _decision(ACTION_REJECT, profile, ["machine_id"], "el perfil pertenece a otro equipo")
    if profile.platform and current.platform and profile.platform != current.platform:
        return _decision(ACTION_REJECT, profile, ["plataforma"], "el perfil pertenece a otro SO")

    # 2. Estado del perfil.
    if profile.status != CalibrationState.VALIDADO:
        return _decision(
            ACTION_RECALIBRATE, profile, ["estado_perfil"],
            "el perfil no esta VALIDADO (%s)" % profile.status.value,
        )

    # 3. Datos incompletos del perfil.
    missing = []
    if not profile.client_size:
        missing.append("client_size")
    if profile.scale_factor is None:
        missing.append("scale_factor")
    if not profile.window_fingerprint:
        missing.append("window_fingerprint")
    if not profile.display_id:
        missing.append("display_id")
    if missing:
        return _decision(
            ACTION_RECALIBRATE, profile, ["datos_incompletos"],
            "perfil con datos incompletos: %s" % ", ".join(missing), mark_obsolete=True,
        )
    incomplete_controls = [
        c.control_id for c in profile.controls if not _valid_normalized_box(c.client_box_normalized)
    ]

    # 4. Version de detector distinta (solo controles afectados).
    detector_affected: List[str] = []
    if current_detector_versions:
        for control in profile.controls:
            for key, version in control.detector_versions.items():
                current_version = current_detector_versions.get(key)
                if current_version is not None and str(current_version) != str(version):
                    detector_affected.append(control.control_id)
                    break

    # 5. Transformacion verificable en el entorno actual.
    if current.window_state in ("minimized", "hidden"):
        return _decision(
            ACTION_REJECT, profile, ["ventana_no_visible"],
            "la ventana esta %s: prepararla antes de usar coordenadas" % current.window_state,
        )
    if not current.client_size or current.client_bounds is None or current.scale_factor is None:
        return _decision(
            ACTION_RECALIBRATE, profile, ["transformacion_no_verificable"],
            "falta area cliente o escala en el entorno actual",
        )

    # 6. Cambios que invalidan toda la geometria relativa.
    changes: List[str] = []
    if abs(float(profile.scale_factor) - float(current.scale_factor)) > SCALE_TOLERANCE:
        changes.append("escala")
    if profile.dpi is not None and current.dpi is not None and int(profile.dpi) != int(current.dpi):
        changes.append("dpi")
    pw, ph = profile.client_size
    cw, ch = current.client_size
    if abs(pw - cw) > CLIENT_SIZE_TOLERANCE or abs(ph - ch) > CLIENT_SIZE_TOLERANCE:
        changes.append("tamano_cliente")
    if profile.window_state and current.window_state and profile.window_state != current.window_state:
        changes.append("estado_ventana")
    profile_layout = profile.metadata.get("layout_hash") if profile.metadata else None
    if profile_layout and current.layout_hash and profile_layout != current.layout_hash:
        changes.append("layout")
    same_display = profile.display_id == current.display_id
    if same_display:
        if profile.display_pixel_size and current.display_pixel_size and tuple(profile.display_pixel_size) != tuple(current.display_pixel_size):
            changes.append("resolucion")
        if profile.orientation and current.orientation and profile.orientation != current.orientation:
            changes.append("orientacion")
    if changes:
        return _decision(
            ACTION_RECALIBRATE, profile, changes,
            "el entorno cambio (%s): relocalizar los controles" % ", ".join(changes),
        )

    # 7. Controles afectados individualmente (datos incompletos / detector).
    affected = sorted(set(incomplete_controls) | set(detector_affected))
    if affected:
        partial_changes = []
        if incomplete_controls:
            partial_changes.append("controles_incompletos")
        if detector_affected:
            partial_changes.append("version_detector")
        if len(affected) >= len(profile.controls):
            return _decision(
                ACTION_RECALIBRATE, profile, partial_changes,
                "todos los controles requieren recalibrar", affected=affected, mark_obsolete=True,
            )
        # Resto de controles utilizable; los afectados se relocalizan.
        base = _evaluate_position(profile, current)
        base.changes = partial_changes + base.changes
        base.affected_controls = affected
        base.usable_controls = [cid for cid in _all_ids(profile) if cid not in set(affected)]
        base.reason = "%s; relocalizar %d control(es)" % (base.reason, len(affected))
        base.mark_obsolete = False
        return base

    return _evaluate_position(profile, current)


def _evaluate_position(profile: CalibrationProfile, current: EnvironmentFingerprint) -> ProfileValidity:
    """Misma escala y tamano: decide entre ``use`` y ``recompute``."""
    changes: List[str] = []
    if profile.display_id != current.display_id:
        changes.append("monitor")
    if profile.topology_fingerprint and current.topology_fingerprint and profile.topology_fingerprint != current.topology_fingerprint:
        changes.append("topologia")
    cached = (profile.absolute_cache or {}).get("client_bounds")
    if cached is None:
        changes.append("sin_cache_absoluta")
    elif current.client_bounds is not None:
        cached_rect = Rect.from_any(cached)
        if cached_rect is None or cached_rect.to_int_tuple() != current.client_bounds.to_int_tuple():
            changes.append("posicion_ventana")
    if changes:
        return _decision(
            ACTION_RECOMPUTE, profile, changes,
            "misma escala y tamano: recalcular absolutas (%s)" % ", ".join(changes),
        )
    return _decision(ACTION_USE, profile, [], "perfil vigente para la ventana y monitor actuales")


# ============================================================================
# RECALCULO DE ABSOLUTAS
# ============================================================================


def _client_rect_of(window: Any) -> Rect:
    client = getattr(window, "client_bounds", None) if not isinstance(window, Rect) else window
    if client is None or not client.is_valid():
        raise CalibrationTransformError("la ventana no expone un area cliente valida")
    return client


def recompute_absolute(profile: CalibrationProfile, window: WindowInfo) -> Dict[str, Tuple[float, float]]:
    """Puntos absolutos (escritorio nativo) de cada control desde su geometria relativa.

    Usa ``safe_point_normalized`` si existe; si no, el centro de la caja
    normalizada. La transformacion es CLIENT_NORMALIZED -> escritorio:
    ``x = client.left + nx * client.width`` (igual para y), con el area
    cliente leida del SO en el mismo espacio que consume el puntero.
    """
    client = _client_rect_of(window)
    points: Dict[str, Tuple[float, float]] = {}
    for control in profile.controls:
        if not _valid_normalized_box(control.client_box_normalized):
            continue
        nx, ny = control.normalized_center()
        points[control.control_id] = (
            client.left + nx * client.width,
            client.top + ny * client.height,
        )
    return points


def recompute_absolute_boxes(profile: CalibrationProfile, window: WindowInfo) -> Dict[str, Tuple[float, float, float, float]]:
    """Cajas absolutas (escritorio nativo) de cada control desde la caja normalizada."""
    client = _client_rect_of(window)
    boxes: Dict[str, Tuple[float, float, float, float]] = {}
    for control in profile.controls:
        if not _valid_normalized_box(control.client_box_normalized):
            continue
        left, top, right, bottom = control.client_box_normalized
        boxes[control.control_id] = (
            client.left + left * client.width,
            client.top + top * client.height,
            client.left + right * client.width,
            client.top + bottom * client.height,
        )
    return boxes


def build_absolute_cache(
    profile: CalibrationProfile,
    window: WindowInfo,
    current: EnvironmentFingerprint,
) -> Dict[str, Any]:
    """Cache absoluta invalidable para el perfil en la ventana actual."""
    client = _client_rect_of(window)
    return {
        "client_bounds": list(client.to_tuple()),
        "display_id": current.display_id,
        "topology_fingerprint": current.topology_fingerprint,
        "coordinate_space": current.coordinate_space,
        "points": {k: [v[0], v[1]] for k, v in recompute_absolute(profile, window).items()},
        "boxes": {k: list(v) for k, v in recompute_absolute_boxes(profile, window).items()},
    }


# ============================================================================
# SERVICIO
# ============================================================================


class CalibrationValidityService:
    """Carga perfiles vigentes para una ventana y publica recursos al Planner.

    Argumentos:
        store: almacen de perfiles (por defecto el global del proceso).
        adapter: adaptador de escritorio (por defecto ``get_desktop_platform()``).
    """

    def __init__(self, store: Optional[CalibrationProfileStore] = None, adapter: Any = None) -> None:
        if store is None:
            from src.hands.calibration.calibration_profile_storage import get_calibration_profile_store

            store = get_calibration_profile_store()
        self.store = store
        self._adapter = adapter

    @property
    def adapter(self) -> Any:
        if self._adapter is None:
            from src.desktop.platform_contract import get_desktop_platform

            self._adapter = get_desktop_platform()
        return self._adapter

    def capture_environment(
        self,
        window_id: int,
        topology: Any = None,
        layout_hash: Optional[str] = None,
    ) -> EnvironmentFingerprint:
        return EnvironmentFingerprint.capture(
            self.adapter,
            window_id,
            machine_id=self.store.machine_id,
            topology=topology,
            layout_hash=layout_hash,
        )

    def load_valid_profile(
        self,
        app_id: str,
        window_id: int,
        current_detector_versions: Optional[Dict[str, str]] = None,
        topology: Any = None,
        layout_hash: Optional[str] = None,
    ) -> Tuple[Optional[CalibrationProfile], ProfileValidity]:
        """Perfil utilizable para la ventana actual o ``None`` y el motivo.

        Si el perfil es utilizable (``use``/``recompute``) se devuelve con la
        cache absoluta recalculada para la ventana actual. Si el problema es
        del propio perfil (``mark_obsolete``), se marca OBSOLETO en el almacen.
        """
        try:
            current = self.capture_environment(window_id, topology=topology, layout_hash=layout_hash)
        except CalibrationEnvironmentError as exc:
            return None, ProfileValidity(False, ACTION_REJECT, ["entorno_no_disponible"], [], str(exc))

        profile = self.store.get_active_profile(app_id, window_fingerprint=current.window_fingerprint())
        if profile is None:
            other = self.store.get_active_profile(app_id)
            validity = evaluate_profile_validity(other, current, current_detector_versions)
            if validity.valid:
                # Huella distinta pero sin cambios detectables: no se reutiliza
                # (la clave de calibracion no coincide).
                validity = _decision(
                    ACTION_RECALIBRATE, other, validity.changes + ["huella_ventana"],
                    "no hay perfil para la huella de ventana actual",
                )
            if other is not None and validity.mark_obsolete:
                self.store.mark_obsolete(app_id, validity.reason, profile_id=other.profile_id)
            return None, validity

        validity = evaluate_profile_validity(profile, current, current_detector_versions)
        if validity.mark_obsolete:
            self.store.mark_obsolete(app_id, validity.reason, profile_id=profile.profile_id)
            return None, validity
        if not validity.valid:
            return None, validity

        win_result = self.adapter.get_window(int(window_id))
        if not win_result.ok or win_result.value is None:
            return None, ProfileValidity(False, ACTION_REJECT, ["ventana_desaparecida"], [], str(win_result.error))
        try:
            cache = build_absolute_cache(profile, win_result.value, current)
        except CalibrationTransformError as exc:
            return None, ProfileValidity(False, ACTION_RECALIBRATE, ["transformacion_no_verificable"], [], str(exc))
        profile.absolute_cache = cache
        if validity.action == ACTION_RECOMPUTE:
            try:
                self.store.update_absolute_cache(profile.profile_id, cache)
            except Exception as exc:  # la cache es prescindible; no bloquea el uso
                logger.warning("No se pudo actualizar la cache absoluta del perfil %s: %s", profile.profile_id, exc)
        return profile, validity

    def invalidate_for_change(self, app_id: str, reason: str) -> int:
        """Marca OBSOLETO todos los perfiles de la aplicacion (cambio explicito)."""
        return self.store.mark_obsolete(app_id, reason)

    def calibration_required(self, app_id: str, window_id: Optional[int] = None) -> bool:
        """True si la aplicacion necesita calibrarse (unico dato para el catalogo)."""
        if window_id is None:
            return not self.store.list_active_profiles(app_id)
        profile, validity = self.load_valid_profile(app_id, window_id)
        return profile is None or not validity.usable_controls

    def resources_for_planner(
        self,
        app_id: str,
        window_id: int,
        current_detector_versions: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Recursos vigentes con accion real para la ventana y monitor actuales.

        Solo controles con ``action_state == VALIDADO`` y un metodo de
        interaccion real; los de puntero exigen ademas geometria VALIDADO.
        Una descripcion del LLM o una caja visual sin validar nunca llegan.
        """
        profile, validity = self.load_valid_profile(app_id, window_id, current_detector_versions)
        if profile is None:
            return []
        usable = set(validity.usable_controls)
        points = (profile.absolute_cache or {}).get("points", {})
        boxes = (profile.absolute_cache or {}).get("boxes", {})
        resources: List[Dict[str, Any]] = []
        for control in profile.controls:
            if control.control_id not in usable or not control.is_actionable():
                continue
            point = points.get(control.control_id)
            box = boxes.get(control.control_id)
            pointer_ready = control.geometric_state == CalibrationState.VALIDADO and point is not None
            resources.append({
                "resource_id": control.resource_id,
                "app_id": app_id,
                "control_id": control.control_id,
                "name": control.name,
                "control_type": control.control_type,
                "interaction_method": control.interaction_method,
                "semantic_state": control.semantic_state.value,
                "geometric_state": control.geometric_state.value,
                "action_state": control.action_state.value,
                "point": tuple(point) if pointer_ready else None,
                "box": tuple(box) if pointer_ready and box is not None else None,
                "coordinate_space": profile.absolute_cache.get("coordinate_space", DESKTOP_PIXELS),
                "display_id": profile.absolute_cache.get("display_id"),
                "window_id": int(window_id),
                "profile_id": profile.profile_id,
                "validity_action": validity.action,
                "confidences": dict(control.confidences),
                "provenance": list(control.provenance),
            })
        return resources


__all__ = [
    "ACTION_USE",
    "ACTION_RECOMPUTE",
    "ACTION_RECALIBRATE",
    "ACTION_REJECT",
    "CalibrationEnvironmentError",
    "CalibrationTransformError",
    "EnvironmentFingerprint",
    "ProfileValidity",
    "evaluate_profile_validity",
    "recompute_absolute",
    "recompute_absolute_boxes",
    "build_absolute_cache",
    "fallback_topology_fingerprint",
    "CalibrationValidityService",
]
