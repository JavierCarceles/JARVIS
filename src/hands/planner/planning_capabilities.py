"""
Capacidades disponibles para planificacion (roadmap 3.8.7.1-3.8.7.4).

Expone al Planner SOLO las capacidades de una aplicacion que estan
sustentadas a la vez por:

1. una capacidad DECLARADA en el catalogo de la aplicacion (nunca inferida por
   estar instalada: rellenar formularios, enviar, guardar o borrar no se deducen
   de nada);
2. una accion REAL registrada en ``ActionRegistry`` y habilitada para el
   planificador;
3. las capacidades del adaptador del SO actual en estado ``DISPONIBLE``
   (contrato de escritorio y contrato de lanzamiento);
4. si la capacidad usa elementos de interfaz, recursos calibrados VIGENTES para
   la ventana actual (``CalibrationValidityService.resources_for_planner``).
   Una descripcion del LLM o una caja visual no habilitan acciones.

Cuando falta algo se informa la capacidad que falta con un codigo estable
(``action_missing``, ``element_not_calibrable``, ``permission_missing``,
``os_capability_unavailable``, ``not_inferable``) e instrucciones si las hay.

El modulo no ejecuta acciones ni lanza aplicaciones. Las dependencias pesadas
(ActionRegistry, contrato de escritorio, servicio de vigencia de calibracion)
se importan de forma perezosa e inyectable.

Relacion con el mapa de estados UI (3.8.6.12): los recursos que publica el
servicio de vigencia ya incluyen los elementos observados en la exploracion;
aqui solo se relacionan aplicacion -> elementos -> accion -> resultado esperado
(efectos de la accion registrada) sin duplicar registros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.core.log import get_logger

logger = get_logger(__name__)

REASON_ACTION_MISSING = "action_missing"
REASON_ELEMENT_NOT_CALIBRABLE = "element_not_calibrable"
REASON_PERMISSION_MISSING = "permission_missing"
REASON_OS_CAPABILITY_UNAVAILABLE = "os_capability_unavailable"
REASON_NOT_INFERABLE = "not_inferable"

# Capacidad declarada -> acciones genericas registradas que la implementan.
CAPABILITY_ACTION_HINTS: Dict[str, Sequence[str]] = {
    "open": ("open_application",),
    "close": ("close_application",),
    "wait": ("wait_for_application_state",),
}

# Capacidad declarada -> capacidades del adaptador del SO necesarias.
# "launch" se consulta en el contrato de lanzamiento; el resto en el de escritorio.
CAPABILITY_OS_REQUIREMENTS: Dict[str, Sequence[str]] = {
    "open": ("launch", "process_verify"),
    "close": ("process_verify", "window_control"),
    "wait": ("process_verify",),
    "screenshot": ("screen_capture",),
    "click": ("input_control", "window_control"),
    "type": ("input_control", "window_control"),
    "navigate": ("input_control", "window_control"),
    "search": ("input_control", "window_control"),
    "scroll": ("input_control", "window_control"),
    "refresh": ("input_control", "window_control"),
    "new_tab": ("input_control", "window_control"),
    "close_tab": ("input_control", "window_control"),
    "switch_tab": ("input_control", "window_control"),
    "zoom": ("input_control", "window_control"),
}

# Capacidades que actuan sobre la interfaz: exigen recursos calibrados vigentes
# aunque el catalogo no liste elementos concretos.
UI_CAPABILITIES = frozenset({
    "click", "type", "navigate", "search", "scroll", "refresh", "new_tab", "close_tab",
    "switch_tab", "zoom", "bookmark", "login", "logout", "download", "upload", "share",
    "print", "export", "import",
})

# Capacidades con efecto irreversible o sensible: nunca se exponen por inferencia.
SENSITIVE_CAPABILITIES = frozenset({
    "login", "logout", "download", "upload", "share", "print", "export", "import",
    "send", "save", "delete", "submit", "fill_form", "purchase", "pay",
})


def _norm(value: Any) -> str:
    raw = getattr(value, "value", value)
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")


@dataclass
class CapabilityExposure:
    """Estado de una capacidad de una aplicacion frente al Planner."""

    app_id: str
    capability: str
    action_name: Optional[str]
    supported: bool
    reason: str
    requires_calibration: bool
    os_capability_status: Dict[str, str] = field(default_factory=dict)
    reason_code: Optional[str] = None
    required_ui_elements: List[str] = field(default_factory=list)
    calibrated_resources: List[str] = field(default_factory=list)
    expected_effects: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "capability": self.capability,
            "action_name": self.action_name,
            "supported": self.supported,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "requires_calibration": self.requires_calibration,
            "os_capability_status": dict(self.os_capability_status),
            "required_ui_elements": list(self.required_ui_elements),
            "calibrated_resources": list(self.calibrated_resources),
            "expected_effects": list(self.expected_effects),
        }


@dataclass
class MissingCapability:
    """Capacidad que falta para que el Planner pueda usar una capacidad."""

    app_id: str
    capability: str
    reason_code: str
    detail: str
    instructions: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "capability": self.capability,
            "reason_code": self.reason_code,
            "detail": self.detail,
            "instructions": self.instructions,
        }


class PlanningCapabilityService:
    """Calcula que capacidades de una aplicacion son planificables ahora."""

    def __init__(
        self,
        registry: Any = None,
        desktop: Any = None,
        validity: Any = None,
        app_manager: Any = None,
        launch_adapter: Any = None,
    ) -> None:
        self._registry = registry
        self._desktop = desktop
        self._validity = validity
        self._app_manager = app_manager
        self._launch_adapter = launch_adapter
        self._os_status_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Dependencias perezosas
    # ------------------------------------------------------------------

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from src.hands.actions.action_registry import get_action_registry

            self._registry = get_action_registry()
        return self._registry

    @property
    def app_manager(self) -> Any:
        if self._app_manager is None:
            from src.hands.apps.applications_core import get_application_manager

            self._app_manager = get_application_manager()
        return self._app_manager

    def _get_desktop(self) -> Any:
        if self._desktop is None:
            try:
                from src.desktop.platform_contract import get_desktop_platform

                self._desktop = get_desktop_platform()
            except Exception as exc:
                logger.warning("Contrato de escritorio no disponible: %s", exc)
                self._desktop = False
        return self._desktop or None

    def _get_launch_adapter(self) -> Any:
        if self._launch_adapter is None:
            try:
                from src.hands.apps.platform_launch import get_launch_adapter

                self._launch_adapter = get_launch_adapter(app_manager=self._app_manager)
            except Exception as exc:
                logger.warning("Adaptador de lanzamiento no disponible: %s", exc)
                self._launch_adapter = False
        return self._launch_adapter or None

    def _get_validity(self) -> Any:
        if self._validity is None:
            try:
                from src.hands.calibration.calibration_validity import CalibrationValidityService

                self._validity = CalibrationValidityService()
            except Exception as exc:
                logger.warning("Servicio de vigencia de calibracion no disponible: %s", exc)
                self._validity = False
        return self._validity or None

    # ------------------------------------------------------------------
    # Estado de capacidades del SO
    # ------------------------------------------------------------------

    def _os_statuses(self) -> Dict[str, Any]:
        """Mapa capacidad -> (estado, detalle, instrucciones) del SO actual."""
        if self._os_status_cache is not None:
            return self._os_status_cache
        statuses: Dict[str, Any] = {}
        desktop = self._get_desktop()
        if desktop is not None:
            try:
                for cap, report in desktop.capabilities().items():
                    statuses[_norm(cap)] = report
            except Exception as exc:
                logger.warning("No se pudieron leer las capacidades del escritorio: %s", exc)
        adapter = self._get_launch_adapter()
        if adapter is not None:
            try:
                for cap, report in adapter.capabilities().items():
                    key = _norm(cap)
                    if key in ("launch", "discover", "resolve", "preflight") or key not in statuses:
                        statuses[key] = report
            except Exception as exc:
                logger.warning("No se pudieron leer las capacidades de lanzamiento: %s", exc)
        self._os_status_cache = statuses
        return statuses

    def refresh(self) -> None:
        """Descarta el estado cacheado de capacidades del SO."""
        self._os_status_cache = None

    # ------------------------------------------------------------------
    # Catalogo y acciones
    # ------------------------------------------------------------------

    def _app(self, app_name: str) -> Any:
        try:
            return self.app_manager.get_application(app_name)
        except Exception as exc:
            logger.warning("Consulta de la aplicacion %s fallo: %s", app_name, exc)
            return None

    @staticmethod
    def _app_id(app: Any, app_name: str) -> str:
        metadata = getattr(app, "metadata", None) or {}
        return str(metadata.get("entity_id") or _norm(getattr(app, "name", app_name)) or _norm(app_name))

    @staticmethod
    def _calibration_key(app: Any, app_name: str) -> str:
        """Clave con la que la calibracion guarda los perfiles de la aplicacion.

        Es la de ``CalibrationManager`` (``_get_storage_application_key`` sobre
        el nombre, que resuelve aliases como chrome/edge/firefox) normalizada
        como en ``UICalibrationPipeline``. No es el ``entity_id`` del catalogo:
        consultar los recursos con el ``entity_id`` nunca encontraria el perfil.
        """
        name = str(getattr(app, "name", "") or app_name or "")
        try:
            from src.hands.calibration.calibration_manager import CalibrationManager
            from src.hands.calibration.calibration_pipeline import _app_key

            return _app_key(CalibrationManager._get_storage_application_key(name) or name)
        except Exception as exc:
            logger.debug("Clave de calibracion no disponible para %s: %s", name, exc)
            return _norm(name)

    @staticmethod
    def _declared(app: Any) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for cap_def in list(getattr(app, "capabilities", None) or []):
            key = _norm(getattr(cap_def, "capability", cap_def))
            if key:
                result.setdefault(key, cap_def)
        return result

    def find_action(self, app: Any, capability: str) -> Any:
        """Accion registrada (``ActionInfo``) que implementa la capacidad o None."""
        cap = _norm(capability)
        app_name = _norm(getattr(app, "name", ""))
        try:
            actions = dict(self.registry.get_all_actions() or {})
        except Exception as exc:
            logger.warning("No se pudo leer el ActionRegistry: %s", exc)
            return None
        specific = []
        generic = []
        for name, info in actions.items():
            if not getattr(info, "planner_enabled", True) or getattr(info, "function", None) is None:
                continue
            info_cap = _norm(getattr(info, "capability", ""))
            info_app = _norm(getattr(info, "application", ""))
            if info_app and info_app == app_name and info_cap in (cap, "%s_application" % cap):
                specific.append(info)
            elif not info_app and (info_cap == cap or name in CAPABILITY_ACTION_HINTS.get(cap, ())):
                generic.append(info)
        if specific:
            return specific[0]
        for hint in CAPABILITY_ACTION_HINTS.get(cap, ()):
            for info in generic:
                if getattr(info, "name", "") == hint:
                    return info
        return generic[0] if generic else None

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def exposed_capabilities(self, app_name: str, window_id: Optional[int] = None) -> List[CapabilityExposure]:
        """Todas las capacidades DECLARADAS con su estado de planificacion."""
        app = self._app(app_name)
        if app is None:
            return []
        app_id = self._app_id(app, app_name)
        result: List[CapabilityExposure] = []
        resources: Optional[List[Dict[str, Any]]] = None
        for cap, cap_def in self._declared(app).items():
            required = [str(e).strip() for e in (getattr(cap_def, "required_ui_elements", None) or []) if str(e).strip()]
            needs_calibration = bool(required) or cap in UI_CAPABILITIES
            if needs_calibration and resources is None:
                resources = self._resources(self._calibration_key(app, app_name), window_id)
            result.append(self._evaluate(app, app_id, cap, cap_def, required, needs_calibration, resources, window_id))
        return result

    def plannable_capabilities(self, app_name: str, window_id: Optional[int] = None) -> List[CapabilityExposure]:
        """Solo las capacidades que el Planner puede usar ahora."""
        return [c for c in self.exposed_capabilities(app_name, window_id) if c.supported]

    def explain_missing(
        self, app_name: str, capability: Any, window_id: Optional[int] = None
    ) -> Optional[MissingCapability]:
        """Que falta para usar ``capability`` en ``app_name`` (None si nada falta)."""
        cap = _norm(capability)
        app = self._app(app_name)
        if app is None:
            return MissingCapability(_norm(app_name), cap, REASON_NOT_INFERABLE,
                                     "La aplicacion no esta en el catalogo global")
        app_id = self._app_id(app, app_name)
        declared = self._declared(app)
        if cap not in declared:
            detail = "La aplicacion no declara la capacidad %s; no se infiere por estar instalada" % cap
            if cap in SENSITIVE_CAPABILITIES:
                detail += " (capacidad sensible: requiere declaracion y accion verificadas)"
            return MissingCapability(app_id, cap, REASON_NOT_INFERABLE, detail)
        for exposure in self.exposed_capabilities(app_name, window_id):
            if exposure.capability != cap:
                continue
            if exposure.supported:
                return None
            instructions = ""
            if exposure.reason_code == REASON_PERMISSION_MISSING:
                for report in self._os_statuses().values():
                    if getattr(getattr(report, "status", None), "value", "") == "SIN_PERMISO":
                        instructions = getattr(report, "instructions", "") or instructions
            return MissingCapability(app_id, cap, exposure.reason_code or REASON_ACTION_MISSING,
                                     exposure.reason, instructions)
        return MissingCapability(app_id, cap, REASON_ACTION_MISSING, "Capacidad no evaluable")

    # ------------------------------------------------------------------
    # Evaluacion
    # ------------------------------------------------------------------

    def _resources(self, app_id: str, window_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        if window_id is None:
            return None
        validity = self._get_validity()
        if validity is None:
            return None
        try:
            return list(validity.resources_for_planner(app_id, window_id) or [])
        except Exception as exc:
            logger.warning("No se pudieron obtener recursos vigentes de %s: %s", app_id, exc)
            return None

    def _evaluate(
        self,
        app: Any,
        app_id: str,
        cap: str,
        cap_def: Any,
        required: List[str],
        needs_calibration: bool,
        resources: Optional[List[Dict[str, Any]]],
        window_id: Optional[int],
    ) -> CapabilityExposure:
        action = self.find_action(app, cap)
        action_name = getattr(action, "name", None) if action is not None else None
        effects = [str(e) for e in (getattr(action, "effects", None) or [])] if action is not None else []
        os_report: Dict[str, str] = {}

        def exposure(supported: bool, reason: str, code: Optional[str], calibrated: Iterable[str] = ()) -> CapabilityExposure:
            return CapabilityExposure(
                app_id=app_id, capability=cap, action_name=action_name, supported=supported,
                reason=reason, requires_calibration=needs_calibration, os_capability_status=os_report,
                reason_code=code, required_ui_elements=list(required),
                calibrated_resources=list(calibrated), expected_effects=effects,
            )

        if action is None:
            return exposure(False, "No hay accion registrada que implemente %s" % cap, REASON_ACTION_MISSING)

        statuses = self._os_statuses()
        for requirement in CAPABILITY_OS_REQUIREMENTS.get(cap, ("input_control",)):
            report = statuses.get(requirement)
            status = getattr(getattr(report, "status", None), "value", None) or "NO_VERIFICADO"
            os_report[requirement] = status
        missing_perm = [k for k, v in os_report.items() if v == "SIN_PERMISO"]
        unavailable = [k for k, v in os_report.items() if v != "DISPONIBLE"]
        if missing_perm:
            return exposure(False, "Falta permiso del SO para: %s" % ", ".join(missing_perm), REASON_PERMISSION_MISSING)
        if unavailable:
            return exposure(False, "Capacidades del SO no disponibles: %s" % ", ".join(
                "%s=%s" % (k, os_report[k]) for k in unavailable), REASON_OS_CAPABILITY_UNAVAILABLE)

        if needs_calibration:
            if resources is None:
                reason = ("Sin ventana actual para validar recursos calibrados" if window_id is None
                          else "No hay recursos calibrados vigentes para la ventana actual")
                return exposure(False, reason, REASON_ELEMENT_NOT_CALIBRABLE)
            available_names = set()
            for res in resources:
                for key in ("name", "control_id", "element", "logical_name"):
                    value = res.get(key) if isinstance(res, dict) else None
                    if value:
                        available_names.add(_norm(value))
            missing = [e for e in required if _norm(e) not in available_names]
            if missing:
                return exposure(False, "Elementos sin calibracion vigente: %s" % ", ".join(missing),
                                REASON_ELEMENT_NOT_CALIBRABLE, sorted(available_names))
            if not required and not available_names:
                return exposure(False, "La capacidad actua sobre la interfaz y no hay recursos vigentes",
                                REASON_ELEMENT_NOT_CALIBRABLE)
            return exposure(True, "Accion registrada, SO disponible y recursos vigentes", None, sorted(available_names))
        return exposure(True, "Accion registrada y capacidades del SO disponibles", None)


_SERVICE: Optional[PlanningCapabilityService] = None


def get_planning_capability_service() -> PlanningCapabilityService:
    """Instancia compartida (las dependencias se resuelven al primer uso)."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PlanningCapabilityService()
    return _SERVICE


__all__ = [
    "CapabilityExposure",
    "MissingCapability",
    "PlanningCapabilityService",
    "get_planning_capability_service",
    "CAPABILITY_ACTION_HINTS",
    "CAPABILITY_OS_REQUIREMENTS",
    "UI_CAPABILITIES",
    "SENSITIVE_CAPABILITIES",
    "REASON_ACTION_MISSING",
    "REASON_ELEMENT_NOT_CALIBRABLE",
    "REASON_PERMISSION_MISSING",
    "REASON_OS_CAPABILITY_UNAVAILABLE",
    "REASON_NOT_INFERABLE",
]
