"""
Pipeline unico de calibracion de interfaces (Windows y macOS).

Es la UNICA via de calibracion de JARVIS: ``CalibrationManager``,
``EnhancedCalibrator`` y los calibradores heredados de navegadores delegan aqui
una sola vez (cubre 3.8.6.13.1, 3.8.6.13.4, el codigo de 3.8.6.13.5 y
3.8.6.14.1-3.8.6.14.4). Todo el acceso al SO pasa por el contrato de escritorio
(``src.desktop.platform_contract``), por lo que el mismo flujo sirve en ambos SO.

Flujo de ``UICalibrationPipeline.calibrate``:

    politica de calibracion (apps bloqueadas: IDE, consolas, juegos, admin)
    -> capacidades del adaptador del SO (monitores, ventanas, captura, accesibilidad)
    -> abrir instancia propia por la ruta de produccion
       (``ApplicationLaunchService``: descubrimiento -> resolucion -> ApplicationPreflight
       -> lanzamiento -> verificacion proceso/ventana) o reutilizar la existente
    -> elegir monitor (politica de producto o de pruebas, sin indices fijos)
    -> mover -> maximizar -> activar y VERIFICAR geometria/primer plano reales
    -> esperar estabilidad visual (sondeo con limite, nunca sleep fijo)
    -> entorno de interaccion (sesion bloqueada, elevacion, contenido protegido,
       overlays, permisos) -> si algo bloquea, se detiene con motivo
    -> instantanea de deteccion (PID/ventana/foco/monitor/escala)
    -> arbol de accesibilidad + captura de la ventana
    -> deteccion: accesibilidad, Qwen3-VL (via UniversalVisualCalibrator) y,
       si el manifiesto los da DISPONIBLES, OmniParser y PaddleOCR
    -> fusion (VisualUIDetectorFusion) -> puerta de calidad
    -> transformar captura -> escritorio -> cliente -> normalizado
    -> punto seguro y verificacion del puntero SIN click (abortar si cambia algo
       entre deteccion y accion)
    -> persistir perfil local por machine_id (SQLite) -> exploracion opcional
    -> cerrar solo lo abierto por JARVIS o restaurar la ventana reutilizada

Se mantienen separados cuatro resultados: elemento descrito, candidato
visual, control con accion demostrada (patron/accion de accesibilidad) y
coordenada fisica vigente (puntero verificado). Una caja visual o una
descripcion del LLM nunca habilita una accion: solo llegan al Planner los
controles con accion real y geometria validada (``resources_for_planner``).

Dependencias entre bloques (se importan de forma perezosa):
``src.desktop.monitor_topology``, ``src.hands.calibration.coordinate_spaces``,
``src.hands.detection.calibration_quality_gate``,
``src.hands.calibration.dynamic_ui``,
``src.hands.calibration.calibration_profile_storage``,
``src.hands.calibration.calibration_validity``,
``src.hands.apps.platform_launch`` y ``src.core.operation_errors``.
"""

from __future__ import annotations

import dataclasses
import os
import re
import tempfile
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.desktop.monitor_topology import TopologyWatcher
from src.desktop.platform_contract import (
    Capability,
    CapabilityStatus,
    DisplayInfo,
    Rect,
    WindowInfo,
)

logger = get_logger(__name__)


# ============================================================================
# CONSTANTES
# ============================================================================

STAGE_PREFLIGHT = "preflight"
STAGE_CAPABILITIES = "capabilities"
STAGE_LAUNCH = "launch"
STAGE_MONITOR = "monitor"
STAGE_WINDOW = "window"
STAGE_STABILITY = "stability"
STAGE_ENVIRONMENT = "environment"
STAGE_ACCESSIBILITY = "accessibility"
STAGE_CAPTURE = "capture"
STAGE_DETECTION = "detection"
STAGE_FUSION = "fusion"
STAGE_QUALITY_GATE = "quality_gate"
STAGE_TRANSFORM = "transform"
STAGE_POINTER = "pointer_verification"
STAGE_PERSISTENCE = "persistence"
STAGE_EXPLORATION = "exploration"

DEPTH_SURFACE = "surface"
DEPTH_DEEP = "deep"
DEPTH_BRANCH = "branch"

POLICY_PRODUCT = "product"
POLICY_TEST = "test"

# Metodos de interaccion persistidos en el perfil.
INTERACTION_ACCESSIBILITY = "accessibility_action"
INTERACTION_POINTER = "pointer"
INTERACTION_NONE = "none"

# Nombres normalizados de navegadores: si se reutiliza una ventana ya abierta
# por el usuario se calibra en una pestana temporal.
BROWSER_KEYS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi", "safari", "chromium")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _app_key(name: Any) -> str:
    """Clave estable de aplicacion: minusculas, sin acentos, ``_`` como separador."""
    text = unicodedata.normalize("NFKD", str(name or "").strip().casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text)).strip("_")


def _to_plain(value: Any) -> Any:
    """Convierte dataclasses/enums/objetos con to_dict en datos planos."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            return value.to_dict()
        except Exception as exc:
            logger.debug("_to_plain: to_dict fallo: %s", exc)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return {k: _to_plain(v) for k, v in dataclasses.asdict(value).items()}
        except Exception as exc:
            logger.debug("_to_plain: asdict fallo: %s", exc)
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain(v) for v in value]
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float)):
        return enum_value
    return str(value)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int_rect(rect: Optional[Rect]) -> Optional[Tuple[int, int, int, int]]:
    return rect.to_int_tuple() if rect is not None and rect.is_valid() else None


# ============================================================================
# INFORMES
# ============================================================================


@dataclass
class ElementReport:
    """Informe de calibracion por elemento (3.8.6.14.3)."""

    control_id: str
    name: str
    sources: List[str] = field(default_factory=list)
    identity: Dict[str, Any] = field(default_factory=dict)
    control_type: str = ""
    interaction_capability: str = ""
    coordinate_space: str = ""
    display_id: Optional[str] = None
    scale_factor: Optional[float] = None
    precision: Dict[str, Any] = field(default_factory=dict)
    allowed_action: str = INTERACTION_NONE
    validity: str = ""
    failure_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "name": self.name,
            "sources": list(self.sources),
            "identity": dict(self.identity),
            "control_type": self.control_type,
            "interaction_capability": self.interaction_capability,
            "coordinate_space": self.coordinate_space,
            "display_id": self.display_id,
            "scale_factor": self.scale_factor,
            "precision": dict(self.precision),
            "allowed_action": self.allowed_action,
            "validity": self.validity,
            "failure_reason": self.failure_reason,
        }


@dataclass
class CalibrationReport:
    """Informe de calibracion por aplicacion (3.8.6.14.3)."""

    app_id: str
    app_name: str
    success: bool = False
    platform: str = ""
    display: Optional[Dict[str, Any]] = None
    topology_fingerprint: str = ""
    window: Optional[Dict[str, Any]] = None
    elements: List[ElementReport] = field(default_factory=list)
    profile_id: Optional[str] = None
    stage_failed: Optional[str] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    exploration: Optional[Dict[str, Any]] = None
    launched_by_jarvis: bool = False
    reused_window: bool = False
    warnings: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    legacy_elements: List[Dict[str, Any]] = field(default_factory=list)

    def validated_elements(self) -> List[ElementReport]:
        return [e for e in self.elements if e.validity == "VALIDADO"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "app_name": self.app_name,
            "success": self.success,
            "platform": self.platform,
            "display": self.display,
            "topology_fingerprint": self.topology_fingerprint,
            "window": self.window,
            "elements": [e.to_dict() for e in self.elements],
            "profile_id": self.profile_id,
            "stage_failed": self.stage_failed,
            "error": self.error,
            "metrics": dict(self.metrics),
            "exploration": self.exploration,
            "launched_by_jarvis": self.launched_by_jarvis,
            "reused_window": self.reused_window,
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
        }


class _StageFailure(Exception):
    """Fallo de una etapa del pipeline con motivo concreto."""

    def __init__(self, stage: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.details = details


@dataclass
class _RunContext:
    """Recursos de una ejecucion para la limpieza garantizada."""

    window: Optional[WindowInfo] = None
    owned: bool = False
    original_window: Optional[WindowInfo] = None
    original_display_id: Optional[str] = None
    temp_files: List[str] = field(default_factory=list)
    browser_tab_open: bool = False
    initial_pointer: Optional[Tuple[float, float]] = None
    pointer_moved: bool = False
    launch_outcome: Any = None
    topology_watcher: Any = None


# ============================================================================
# PIPELINE
# ============================================================================


class UICalibrationPipeline:
    """Pipeline unico de calibracion sobre el contrato de escritorio.

    Todas las dependencias son inyectables; por defecto se crean de forma
    perezosa con las implementaciones de produccion.

    Argumentos:
        adapter: ``DesktopPlatformAdapter`` (por defecto ``get_desktop_platform()``).
        launcher: servicio con ``open(app_name, timeout=...)`` que devuelve un
            ``LaunchOutcome`` (por defecto ``ApplicationLaunchService``).
        store: ``CalibrationProfileStore`` (persistencia SQLite por machine_id).
        gate: ``CalibrationQualityGate``.
        thresholds: ``DetectionThresholds`` para la puerta de calidad.
        monitor_policy: objeto con ``select(topology, ...)``; si no se da, se usa
            ``TargetMonitorPolicy`` (producto) o ``TestMonitorPolicy`` (pruebas).
        vision: ``UniversalVisualCalibrator`` (o compatible) para Qwen3-VL.
        calibration_policy_checker: ``callable(app_info) -> resultado`` con
            ``allowed``/``reason`` (filtros de calibracion del CalibrationManager).
        use_optional_detectors: consulta el manifiesto para OmniParser/PaddleOCR.
        max_pointer_checks: maximo de controles cuyo punto seguro se verifica
            moviendo el puntero (nunca se hace click).
        stability_timeout: limite de espera de estabilidad visual (segundos).
        vision_timeout: espera maxima de la llamada a Qwen3-VL (segundos).
        vision_max_side: lado mayor (px) de la copia de la captura que se
            envia a Qwen3-VL.
        vision_max_elements: elementos que se piden a Qwen3-VL.
    """

    def __init__(
        self,
        adapter: Any = None,
        launcher: Any = None,
        store: Any = None,
        gate: Any = None,
        thresholds: Any = None,
        monitor_policy: Any = None,
        vision: Any = None,
        calibration_policy_checker: Optional[Callable[[Dict[str, Any]], Any]] = None,
        use_optional_detectors: bool = True,
        max_pointer_checks: int = 40,
        stability_timeout: float = 8.0,
        launch_timeout: float = 15.0,
        explorer_budget: Any = None,
        explorer_policy: Any = None,
        manifest: Any = None,
        fusion: Any = None,
        pointer_verifier: Any = None,
        validity_service: Any = None,
        vision_timeout: float = 300.0,
        vision_max_side: int = 1600,
        vision_max_elements: int = 40,
        visual_detectors: str = "auto",
        min_accessible_controls: int = 5,
        explore_navigation: bool = False,
        navigation_containers: Optional[Sequence[str]] = None,
    ) -> None:
        self._adapter = adapter
        self._launcher = launcher
        self._store = store
        self._gate = gate
        self._thresholds = thresholds
        self._monitor_policy = monitor_policy
        self._vision = vision
        self.calibration_policy_checker = calibration_policy_checker
        self.use_optional_detectors = bool(use_optional_detectors)
        self.max_pointer_checks = int(max_pointer_checks)
        self.stability_timeout = float(stability_timeout)
        self.launch_timeout = float(launch_timeout)
        self.explorer_budget = explorer_budget
        self.explorer_policy = explorer_policy
        self._manifest = manifest
        self._fusion = fusion
        self._pointer_verifier = pointer_verifier
        self._validity_service = validity_service
        # Qwen3-VL: espera maxima de la llamada a Ollama (un servidor colgado
        # no debe bloquear la calibracion) y lado mayor de la imagen enviada
        # (acota los tokens de imagen para que quepan prompt y respuesta en
        # num_ctx). Las cajas vuelven normalizadas 0..1000, asi que reducir la
        # imagen no cambia su conversion a pixeles de la captura original.
        self.vision_timeout = float(vision_timeout)
        self.vision_max_side = int(vision_max_side)
        # Elementos pedidos a Qwen3-VL (complementa a la accesibilidad, que
        # aporta la mayoria de controles) y salida maxima acorde (~60 tokens
        # por elemento): acota el tiempo de generacion, sobre todo sin GPU.
        self.vision_max_elements = int(vision_max_elements)
        # Deteccion visual (Qwen3-VL, OmniParser, PaddleOCR): "auto" solo
        # cuando la accesibilidad no basta (menos de min_accessible_controls
        # controles accionables o sin arbol); "always" siempre; "never" nunca.
        if visual_detectors not in ("auto", "always", "never"):
            raise ValueError("visual_detectors debe ser 'auto', 'always' o 'never'")
        self.visual_detectors = visual_detectors
        self.min_accessible_controls = int(min_accessible_controls)
        # Exploracion profunda: seleccionar elementos de listas de navegacion
        # (panel de Ajustes, lista de conversaciones) solo si se pide; ante la
        # duda no se pulsa (regla de exploracion segura).
        self.explore_navigation = bool(explore_navigation)
        # Solo se navega dentro de estos contenedores (por defecto el panel de
        # navegacion de WinUI): fuera, una lista puede ser de valores.
        self.navigation_containers = navigation_containers
        self._lock = threading.Lock()
        self._wait_event = threading.Event()

    # ------------------------------------------------------------------
    # Dependencias perezosas
    # ------------------------------------------------------------------

    @property
    def adapter(self) -> Any:
        if self._adapter is None:
            from src.desktop.platform_contract import get_desktop_platform

            self._adapter = get_desktop_platform()
        return self._adapter

    @property
    def launcher(self) -> Any:
        if self._launcher is None:
            from src.hands.apps.platform_launch import ApplicationLaunchService

            self._launcher = ApplicationLaunchService(desktop=self.adapter)
        return self._launcher

    @property
    def store(self) -> Any:
        if self._store is None:
            from src.hands.calibration.calibration_profile_storage import CalibrationProfileStore

            self._store = CalibrationProfileStore()
            self._store.initialize()
        return self._store

    @property
    def gate(self) -> Any:
        if self._gate is None:
            from src.hands.detection.calibration_quality_gate import CalibrationQualityGate

            self._gate = CalibrationQualityGate(thresholds=self._thresholds, adapter=self.adapter)
        return self._gate

    @property
    def fusion(self) -> Any:
        if self._fusion is None:
            from src.eyes.detection.visual_ui_detector_fusion import VisualUIDetectorFusion

            self._fusion = VisualUIDetectorFusion()
        return self._fusion

    @property
    def pointer_verifier(self) -> Any:
        if self._pointer_verifier is None:
            from src.hands.calibration.coordinate_spaces import PointerVerifier

            self._pointer_verifier = PointerVerifier(adapter=self.adapter)
        return self._pointer_verifier

    @property
    def validity_service(self) -> Any:
        if self._validity_service is None:
            from src.hands.calibration.calibration_validity import CalibrationValidityService

            self._validity_service = CalibrationValidityService(store=self.store, adapter=self.adapter)
        return self._validity_service

    def _vision_calibrator(self) -> Any:
        if self._vision is None:
            from src.hands.calibration.universal_visual_calibrator import UniversalVisualCalibrator

            self._vision = UniversalVisualCalibrator()
        return self._vision

    def _detector_manifest(self) -> Any:
        if self._manifest is None:
            # Compartido en el proceso: comprobar la disponibilidad carga los
            # modelos y no debe repetirse en cada calibracion.
            from src.hands.detection.detector_manifest import obtener_manifiesto

            self._manifest = obtener_manifiesto()
        return self._manifest

    def _select_policy(self, policy: str) -> Any:
        if self._monitor_policy is not None:
            return self._monitor_policy
        from src.desktop.monitor_topology import TargetMonitorPolicy, TestMonitorPolicy

        if policy == POLICY_TEST:
            return TestMonitorPolicy()
        return TargetMonitorPolicy()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def calibrate(
        self,
        app: Any,
        monitor_reference: Any = None,
        policy: str = POLICY_PRODUCT,
        depth: str = DEPTH_SURFACE,
        branch_ref: Any = None,
        reuse_window: bool = True,
    ) -> CalibrationReport:
        """Calibra una aplicacion por el flujo unico y devuelve el informe.

        Argumentos:
            app: nombre o dict ``{"name", "app_key"?}``. ``app_key`` es la clave
                estable de almacenamiento (por defecto el nombre normalizado).
            monitor_reference: ``None`` (politica), texto del usuario ("la de la
                izquierda"), ``DisplayInfo``, ``"display:<id>"`` o entero de
                compatibilidad (``monitor_id`` de ScreenManager, resuelto por
                geometria real, nunca por indice).
            policy: ``"product"`` (regla 4) o ``"test"`` (regla 5).
            depth: ``"surface"``, ``"deep"`` (exploracion completa dentro del
                presupuesto) o ``"branch"`` (solo la rama de ``branch_ref``).
            reuse_window: reutiliza una ventana ya abierta (y la restaura al
                terminar) en lugar de exigir una instancia nueva.
        """
        if policy not in (POLICY_PRODUCT, POLICY_TEST):
            raise ValueError("policy debe ser 'product' o 'test'")
        if depth not in (DEPTH_SURFACE, DEPTH_DEEP, DEPTH_BRANCH):
            raise ValueError("depth debe ser 'surface', 'deep' o 'branch'")
        if depth == DEPTH_BRANCH and not branch_ref:
            raise ValueError("depth='branch' requiere branch_ref")

        app_info = self._app_info(app)
        report = CalibrationReport(app_id=app_info["app_key"], app_name=app_info["name"])
        report.metrics["timings"] = {}
        report.metrics["policy"] = policy
        report.metrics["depth"] = depth
        ctx = _RunContext()
        started = time.monotonic()

        with self._lock:
            try:
                self._run(app_info, report, ctx, monitor_reference, policy, depth, branch_ref, reuse_window)
            except _StageFailure as failure:
                report.success = False
                report.stage_failed = failure.stage
                report.error = failure.message
                if failure.details:
                    report.evidence[failure.stage] = self._redact(_to_plain(failure.details))
                logger.warning(
                    "[CALIBRATION-PIPELINE] %s: fallo en etapa %s: %s",
                    report.app_name, failure.stage, failure.message,
                )
            except Exception as exc:  # error inesperado: nunca exito falso
                logger.exception("[CALIBRATION-PIPELINE] error inesperado calibrando %s", report.app_name)
                report.success = False
                report.stage_failed = report.stage_failed or "unexpected"
                report.error = "error inesperado: %s" % exc
            finally:
                self._cleanup(ctx, report)
                report.metrics["total_seconds"] = round(time.monotonic() - started, 3)
        logger.info(
            "[CALIBRATION-PIPELINE] %s: exito=%s validados=%d etapa_fallida=%s",
            report.app_name, report.success, len(report.validated_elements()), report.stage_failed,
        )
        return report

    def resources_for_planner(self, app_id: str, window_id: int) -> List[Dict[str, Any]]:
        """Recursos vigentes con accion real para la ventana actual (3.8.6.14.4).

        Delega en ``CalibrationValidityService`` (solo controles VALIDADO con
        punto recalculado para la ventana actual) y descarta cualquier recurso
        sin metodo de interaccion real.
        """
        try:
            resources = self.validity_service.resources_for_planner(_app_key(app_id), int(window_id)) or []
        except Exception as exc:
            logger.warning("[CALIBRATION-PIPELINE] recursos para el Planner no disponibles: %s", exc)
            return []
        result = []
        for resource in resources:
            method = _get(resource, "interaction_method", INTERACTION_NONE)
            if method and method != INTERACTION_NONE:
                result.append(_to_plain(resource))
        return result

    def recover_profile(self, app_id: str, window_id: int) -> Dict[str, Any]:
        """Recupera el perfil tras reiniciar SOLO si el fingerprint coincide (3.8.6.13.4)."""
        info: Dict[str, Any] = {"app_id": _app_key(app_id), "window_id": int(window_id), "recovered": False}
        try:
            profile, validity = self.validity_service.load_valid_profile(_app_key(app_id), int(window_id))
        except Exception as exc:
            info["error"] = str(exc)
            return info
        info["validity"] = _to_plain(validity)
        action = _get(validity, "action", "reject")
        info["recovered"] = bool(profile is not None and _get(validity, "valid", False) and action in ("use", "recompute"))
        if profile is not None:
            info["profile"] = {
                "profile_id": _get(profile, "profile_id"),
                "topology_fingerprint": _get(profile, "topology_fingerprint"),
                "window_fingerprint": _get(profile, "window_fingerprint"),
                "display_id": _get(profile, "display_id"),
                "scale_factor": _get(profile, "scale_factor"),
                "dpi": _get(profile, "dpi"),
                "status": _to_plain(_get(profile, "status")),
                "controls": len(_get(profile, "controls", []) or []),
            }
        try:
            window = self.adapter.get_window(int(window_id))
            if window.ok and window.value is not None:
                info["window"] = self._window_summary(window.value)
        except Exception as exc:
            info.setdefault("warnings", []).append("ventana no disponible: %s" % exc)
        return info

    # ------------------------------------------------------------------
    # Ejecucion
    # ------------------------------------------------------------------

    def _timed(self, report: CalibrationReport, stage: str, started: float) -> None:
        report.metrics["timings"][stage] = round(time.monotonic() - started, 3)

    def _run(
        self,
        app_info: Dict[str, Any],
        report: CalibrationReport,
        ctx: _RunContext,
        monitor_reference: Any,
        policy: str,
        depth: str,
        branch_ref: Any,
        reuse_window: bool,
    ) -> None:
        t = time.monotonic()
        self._stage_policy(app_info)
        self._timed(report, STAGE_PREFLIGHT, t)

        adapter = self.adapter
        report.platform = str(getattr(adapter, "platform_name", "") or "")

        t = time.monotonic()
        caps = self._stage_capabilities(adapter, report)
        self._timed(report, STAGE_CAPABILITIES, t)

        t = time.monotonic()
        window = self._stage_launch(app_info, ctx, report, reuse_window)
        self._timed(report, STAGE_LAUNCH, t)

        t = time.monotonic()
        topology, display = self._stage_monitor(adapter, window, monitor_reference, policy, report, ctx)
        self._timed(report, STAGE_MONITOR, t)

        t = time.monotonic()
        if ctx.topology_watcher is not None and not ctx.topology_watcher.assert_unchanged(topology.fingerprint):
            raise _StageFailure(STAGE_WINDOW, "la topologia de monitores cambio antes de preparar la ventana")
        window = self._stage_prepare_window(adapter, window, display, topology)
        ctx.window = window
        report.window = self._window_summary(window)
        self._timed(report, STAGE_WINDOW, t)

        if not ctx.owned and self._is_browser(app_info["name"]):
            ctx.browser_tab_open = self._open_temporary_tab(adapter, window)
            if not ctx.browser_tab_open:
                raise _StageFailure(STAGE_WINDOW, "no se pudo abrir la pestana temporal de calibracion")

        capture_ok = caps.get(Capability.SCREEN_CAPTURE) == CapabilityStatus.DISPONIBLE
        access_ok = caps.get(Capability.ACCESSIBILITY_TREE) == CapabilityStatus.DISPONIBLE

        t = time.monotonic()
        self._stage_stability(adapter, window, capture_ok, report)
        self._timed(report, STAGE_STABILITY, t)

        t = time.monotonic()
        self._stage_environment(adapter, window, report)
        self._timed(report, STAGE_ENVIRONMENT, t)

        from src.hands.detection.calibration_quality_gate import take_detection_snapshot

        snapshot = take_detection_snapshot(adapter, window.window_id, topology=topology)

        t = time.monotonic()
        tree = self._stage_accessibility(adapter, window, access_ok, report)
        self._timed(report, STAGE_ACCESSIBILITY, t)

        t = time.monotonic()
        if ctx.topology_watcher is not None and not ctx.topology_watcher.assert_unchanged(topology.fingerprint):
            raise _StageFailure(STAGE_CAPTURE, "la topologia de monitores cambio antes de capturar")
        capture, image_path = self._stage_capture(adapter, window, capture_ok, ctx, report)
        self._timed(report, STAGE_CAPTURE, t)

        if tree is None and capture is None:
            raise _StageFailure(STAGE_DETECTION, "sin accesibilidad ni captura: nada que calibrar")

        from src.hands.calibration.coordinate_spaces import CoordinateTransformer, TransformContext

        transformer = CoordinateTransformer(
            TransformContext(platform=report.platform, display=display, window=window, capture=capture)
        )

        t = time.monotonic()
        candidates, work_space = self._stage_detection(
            app_info, tree, capture, image_path, window, transformer, report
        )
        self._timed(report, STAGE_DETECTION, t)

        t = time.monotonic()
        fused = self._stage_fusion(candidates, image_path, window, report)
        self._timed(report, STAGE_FUSION, t)

        t = time.monotonic()
        gate_result, window_rect_work = self._stage_quality_gate(
            fused, window, transformer, work_space, capture, report
        )
        self._timed(report, STAGE_QUALITY_GATE, t)

        t = time.monotonic()
        if ctx.topology_watcher is not None and not ctx.topology_watcher.assert_unchanged(topology.fingerprint):
            raise _StageFailure(STAGE_POINTER, "la topologia de monitores cambio antes de verificar el puntero")
        records = self._stage_transform_and_verify(
            app_info, gate_result, transformer, work_space, window, display, snapshot, ctx, report
        )
        self._timed(report, STAGE_POINTER, t)

        t = time.monotonic()
        self._stage_persist(app_info, records, window, display, topology, report)
        self._timed(report, STAGE_PERSISTENCE, t)

        validated = report.validated_elements()
        report.success = bool(validated)
        if not validated:
            report.stage_failed = STAGE_POINTER
            report.error = "ningun control supero la verificacion geometrica"

        if depth in (DEPTH_DEEP, DEPTH_BRANCH):
            t = time.monotonic()
            self._stage_exploration(
                app_info, window, depth, branch_ref, access_ok, report,
                ctx=ctx, display=display, topology=topology,
            )
            self._timed(report, STAGE_EXPLORATION, t)

    # ------------------------------------------------------------------
    # Etapas
    # ------------------------------------------------------------------

    def _app_info(self, app: Any) -> Dict[str, Any]:
        if isinstance(app, dict):
            name = str(app.get("name") or app.get("display_name") or "").strip()
            key = str(app.get("app_key") or "").strip() or _app_key(name)
            info = dict(app)
            info["name"] = name
            info["app_key"] = _app_key(key)
        else:
            name = str(app or "").strip()
            info = {"name": name, "app_key": _app_key(name)}
        if not info["name"] or not info["app_key"]:
            raise ValueError("Nombre de aplicacion vacio")
        return info

    def _stage_policy(self, app_info: Dict[str, Any]) -> None:
        """Politica de calibracion (no sustituye a ApplicationPreflight, que
        ejecuta el lanzador antes de abrir)."""
        try:
            policy = getattr(self._vision, "policy", None)
            if policy is None:
                from src.hands.calibration.universal_visual_calibrator import CalibrationPolicy

                policy = CalibrationPolicy()
            allowed, reason = policy.can_calibrate_application(app_info["name"])
        except Exception as exc:
            raise _StageFailure(STAGE_PREFLIGHT, "politica de calibracion no disponible: %s" % exc)
        if not allowed:
            raise _StageFailure(STAGE_PREFLIGHT, str(reason or "aplicacion bloqueada para calibracion"))
        if self.calibration_policy_checker is not None:
            try:
                result = self.calibration_policy_checker(app_info)
            except Exception as exc:
                raise _StageFailure(STAGE_PREFLIGHT, "error en el filtro de calibracion: %s" % exc)
            allowed = _get(result, "allowed", None)
            if allowed is None and isinstance(result, bool):
                allowed = result
            if not allowed:
                raise _StageFailure(
                    STAGE_PREFLIGHT,
                    str(_get(result, "reason", None) or "aplicacion rechazada por el filtro de calibracion"),
                )

    def _stage_capabilities(self, adapter: Any, report: CalibrationReport) -> Dict[Any, Any]:
        try:
            reports = adapter.capabilities()
        except Exception as exc:
            raise _StageFailure(STAGE_CAPABILITIES, "no se pudieron leer las capacidades del SO: %s" % exc)
        statuses = {cap: _get(rep, "status") for cap, rep in reports.items()}
        report.metrics["capabilities"] = {
            getattr(cap, "value", str(cap)): _to_plain(status) for cap, status in statuses.items()
        }
        missing = [
            cap for cap in (Capability.DISPLAY_ENUM, Capability.WINDOW_CONTROL, Capability.WINDOW_VERIFY)
            if statuses.get(cap) != CapabilityStatus.DISPONIBLE
        ]
        if missing:
            details = {
                getattr(c, "value", str(c)): {
                    "status": _to_plain(statuses.get(c)),
                    "instructions": _get(reports.get(c), "instructions", ""),
                }
                for c in missing
            }
            raise _StageFailure(
                STAGE_CAPABILITIES,
                "capacidades del SO no disponibles: %s" % ", ".join(getattr(c, "value", str(c)) for c in missing),
                capabilities=details,
            )
        for cap in (Capability.SCREEN_CAPTURE, Capability.ACCESSIBILITY_TREE, Capability.INPUT_CONTROL):
            if statuses.get(cap) != CapabilityStatus.DISPONIBLE:
                report.warnings.append(
                    "capacidad %s no disponible (%s): %s"
                    % (cap.value, _to_plain(statuses.get(cap)), _get(reports.get(cap), "instructions", ""))
                )
        return statuses

    def _stage_launch(
        self, app_info: Dict[str, Any], ctx: _RunContext, report: CalibrationReport, reuse_window: bool
    ) -> WindowInfo:
        try:
            outcome = self.launcher.open(app_info["name"], timeout=self.launch_timeout)
        except Exception as exc:
            raise _StageFailure(STAGE_LAUNCH, "el lanzador fallo: %s" % exc)
        ctx.launch_outcome = outcome
        if not _get(outcome, "success", False):
            error = _get(outcome, "error")
            raise _StageFailure(
                STAGE_LAUNCH,
                str(_get(error, "message", None) or error or "no se pudo abrir la aplicacion"),
                error=self._redact(_to_plain(error)),
            )
        window = _get(outcome, "window")
        if window is None:
            raise _StageFailure(STAGE_LAUNCH, "la aplicacion se abrio pero no se verifico ninguna ventana GUI")
        reused = bool(_get(outcome, "reused_existing", False))
        if reused and not reuse_window:
            raise _StageFailure(STAGE_LAUNCH, "la aplicacion ya estaba abierta y no se permite reutilizarla")
        ctx.window = window
        ctx.owned = not reused
        report.launched_by_jarvis = not reused
        report.reused_window = reused
        if reused:
            # Estado original de la ventana del usuario para restaurarlo.
            current = self.adapter.get_window(window.window_id)
            ctx.original_window = current.value if current.ok and current.value is not None else window
            ctx.original_display_id = _get(ctx.original_window, "display_id")
        report.evidence["launch"] = self._redact(_to_plain(_get(outcome, "evidence", {}) or {}))
        return window

    def _stage_monitor(
        self,
        adapter: Any,
        window: WindowInfo,
        monitor_reference: Any,
        policy: str,
        report: CalibrationReport,
        ctx: Any = None,
    ) -> Tuple[Any, DisplayInfo]:
        from src.desktop.monitor_topology import get_current_topology, resolve_monitor_reference

        try:
            topology = get_current_topology(adapter)
        except Exception as exc:
            raise _StageFailure(STAGE_MONITOR, "no se pudo enumerar la topologia de monitores: %s" % exc)
        report.topology_fingerprint = str(getattr(topology, "fingerprint", "") or "")
        report.metrics["displays"] = len(getattr(topology, "displays", []) or [])
        # Establecer la topologia de referencia para detectar cambios antes de
        # cada accion espacial (mover ventana, capturar, mover puntero).
        try:
            watcher = TopologyWatcher(adapter)
            watcher.baseline()
            ctx.topology_watcher = watcher
        except Exception as exc:
            logger.warning("[CALIBRATION-PIPELINE] no se pudo establecer el baseline de topologia: %s", exc)

        display: Optional[DisplayInfo] = None
        source = ""
        if isinstance(monitor_reference, DisplayInfo):
            display = topology.get(monitor_reference.display_id)
            source = "display_info"
        elif isinstance(monitor_reference, bool):
            raise _StageFailure(STAGE_MONITOR, "referencia de monitor invalida")
        elif isinstance(monitor_reference, int):
            display = self._display_for_legacy_screen(int(monitor_reference), topology)
            source = "legacy_screen_number"
            if display is None:
                raise _StageFailure(STAGE_MONITOR, "monitor %s no encontrado en la topologia actual" % monitor_reference)
        elif isinstance(monitor_reference, str) and monitor_reference.startswith("display:"):
            display = topology.get(monitor_reference[len("display:"):])
            source = "display_id"
        elif isinstance(monitor_reference, str) and monitor_reference.strip():
            resolved = resolve_monitor_reference(monitor_reference, topology, current_display_id=window.display_id)
            status = _get(resolved, "status")
            if status == "ambiguous":
                raise _StageFailure(
                    STAGE_MONITOR,
                    "referencia de monitor ambigua: %s" % _get(resolved, "reason", ""),
                    candidates=[_get(c, "display_id") for c in _get(resolved, "candidates", []) or []],
                )
            display = _get(resolved, "display")
            source = "user_reference"
        if monitor_reference is not None and display is None:
            raise _StageFailure(STAGE_MONITOR, "monitor solicitado no encontrado: %s" % monitor_reference)

        if display is None:
            selector = self._select_policy(policy)
            try:
                if policy == POLICY_TEST and self._monitor_policy is None:
                    selection = selector.select(topology)
                else:
                    try:
                        # Regla 4: si la app ya esta abierta y no se pide otro
                        # monitor, se queda donde esta.
                        selection = selector.select(topology, window=window)
                    except TypeError:
                        selection = selector.select(topology)
            except Exception as exc:
                raise _StageFailure(STAGE_MONITOR, "la politica de monitor fallo: %s" % exc)
            if _get(selection, "ambiguous", False):
                raise _StageFailure(
                    STAGE_MONITOR,
                    "seleccion de monitor ambigua: %s" % _get(selection, "reason", ""),
                    candidates=[_get(c, "display_id") for c in _get(selection, "candidates", []) or []],
                )
            display = _get(selection, "display")
            source = "policy:%s:%s" % (policy, _get(selection, "source", ""))
        if display is None:
            raise _StageFailure(STAGE_MONITOR, "no se pudo determinar el monitor destino")
        report.display = _to_plain(display)
        report.metrics["display_source"] = source
        return topology, display

    def _display_for_legacy_screen(self, screen_number: int, topology: Any) -> Optional[DisplayInfo]:
        """Resuelve un ``monitor_id`` de ScreenManager por geometria real (sin indices)."""
        try:
            from src.desktop.screen_manager import get_screen_manager

            manager = get_screen_manager()
            manager.refresh_monitors()
            monitor = manager.get_monitor(int(screen_number))
        except Exception as exc:
            logger.debug("[CALIBRATION-PIPELINE] ScreenManager no disponible: %s", exc)
            return None
        if monitor is None:
            return None
        target = (int(monitor.left), int(monitor.top), int(monitor.right), int(monitor.bottom))
        for display in getattr(topology, "displays", []) or []:
            if display.bounds.to_int_tuple() == target:
                return display
        return None

    def legacy_screen_number(self, display: Any) -> int:
        """``monitor_id`` de ScreenManager del monitor dado (0 si no coincide)."""
        bounds = _get(display, "bounds")
        if isinstance(bounds, dict):
            rect = Rect.from_any(bounds)
        else:
            rect = bounds if isinstance(bounds, Rect) else None
        if rect is None:
            return 0
        try:
            from src.desktop.screen_manager import get_screen_manager

            manager = get_screen_manager()
            target = rect.to_int_tuple()
            for monitor in getattr(manager, "monitors", []) or []:
                if (int(monitor.left), int(monitor.top), int(monitor.right), int(monitor.bottom)) == target:
                    return int(monitor.monitor_id)
        except Exception as exc:
            logger.debug("[CALIBRATION-PIPELINE] legacy_screen_number: %s", exc)
        return 0

    def _stage_prepare_window(
        self, adapter: Any, window: WindowInfo, display: DisplayInfo, topology: Any
    ) -> WindowInfo:
        wid = int(window.window_id)
        if window.is_minimized:
            res = adapter.restore_window(wid)
            if not res.ok:
                raise _StageFailure(STAGE_WINDOW, "no se pudo restaurar la ventana: %s" % res.error)
        current = self._read_window(adapter, wid)
        current_display = self._display_of(current, topology)
        if current_display is None or current_display.display_id != display.display_id:
            res = adapter.move_window_to_display(wid, display.display_id)
            if not res.ok:
                raise _StageFailure(STAGE_WINDOW, "no se pudo mover la ventana al monitor destino: %s" % res.error)
        res = adapter.maximize_window(wid)
        if not res.ok:
            raise _StageFailure(STAGE_WINDOW, "no se pudo maximizar la ventana: %s" % res.error)
        res = adapter.activate_window(wid)
        if not res.ok:
            raise _StageFailure(STAGE_WINDOW, "la ventana no quedo en primer plano: %s" % res.error)

        prepared = self._read_window(adapter, wid)
        if prepared.is_minimized or not prepared.is_visible:
            raise _StageFailure(STAGE_WINDOW, "la ventana no esta visible tras prepararla")
        if not (prepared.is_foreground or adapter.is_foreground(wid)):
            raise _StageFailure(STAGE_WINDOW, "la ventana no esta en primer plano tras activarla")
        prepared_display = self._display_of(prepared, topology)
        if prepared_display is None or prepared_display.display_id != display.display_id:
            raise _StageFailure(
                STAGE_WINDOW,
                "la ventana no quedo en el monitor destino",
                expected=display.display_id,
                actual=_get(prepared_display, "display_id"),
            )
        frame = prepared.frame_bounds or prepared.bounds
        coverage = 0.0
        if frame is not None and display.work_area.area > 0:
            coverage = frame.intersection_area(display.work_area) / display.work_area.area
        if not prepared.is_maximized and coverage < 0.9:
            raise _StageFailure(
                STAGE_WINDOW,
                "la ventana no quedo maximizada (cobertura del area util %.2f)" % coverage,
            )
        return prepared

    @staticmethod
    def _read_window(adapter: Any, window_id: int) -> WindowInfo:
        res = adapter.get_window(int(window_id))
        if not res.ok or res.value is None:
            raise _StageFailure(STAGE_WINDOW, "la ventana %s ya no existe: %s" % (window_id, res.error))
        return res.value

    @staticmethod
    def _display_of(window: WindowInfo, topology: Any) -> Optional[DisplayInfo]:
        rect = window.frame_bounds or window.bounds
        if rect is None:
            return topology.get(window.display_id) if window.display_id else None
        return topology.display_for_rect(rect)

    def _stage_stability(self, adapter: Any, window: WindowInfo, capture_ok: bool, report: CalibrationReport) -> None:
        """Espera a que la interfaz deje de cambiar (sondeo con limite, sin sleep fijo)."""
        wid = int(window.window_id)
        stable = False
        method = ""
        if capture_ok:
            from src.hands.calibration.dynamic_ui import UIChangeDetector

            def _capture_frame() -> Any:
                res = adapter.capture_window(wid)
                return res.value.image if res.ok and res.value is not None else None

            try:
                result = UIChangeDetector().wait_until_stable(
                    _capture_frame, timeout=self.stability_timeout, stable_frames=3
                )
                stable = bool(_get(result, "stable", result if isinstance(result, bool) else False))
                method = "frames"
                report.metrics["stability"] = _to_plain(result)
            except Exception as exc:
                report.warnings.append("estabilidad visual no evaluable: %s" % exc)
        if not stable:
            stable = self._wait_tree_stable(adapter, window)
            method = method + "+tree" if method else "tree"
        report.metrics["stability_method"] = method
        if not stable:
            raise _StageFailure(STAGE_STABILITY, "la interfaz no se estabilizo en %.1f s" % self.stability_timeout)

    def _wait_tree_stable(self, adapter: Any, window: WindowInfo, required: int = 3, poll: float = 0.2) -> bool:
        deadline = time.monotonic() + self.stability_timeout
        last = None
        same = 0
        while time.monotonic() < deadline:
            res = adapter.get_accessibility_tree(int(window.window_id), pid=window.pid)
            if not res.ok or res.value is None:
                return False
            current = res.value.structure_hash()
            same = same + 1 if current == last else 1
            last = current
            if same >= required:
                return True
            self._wait_event.wait(poll)
        return False

    def _stage_environment(self, adapter: Any, window: WindowInfo, report: CalibrationReport) -> None:
        from src.hands.detection.calibration_quality_gate import check_interaction_environment

        check = check_interaction_environment(adapter, int(window.window_id))
        report.evidence["environment"] = _to_plain(_get(check, "environment"))
        if not _get(check, "allowed", False):
            raise _StageFailure(
                STAGE_ENVIRONMENT,
                "el entorno no permite capturar ni interactuar: %s" % ", ".join(_get(check, "reasons", []) or []),
                reasons=list(_get(check, "reasons", []) or []),
            )

    def _stage_accessibility(self, adapter: Any, window: WindowInfo, access_ok: bool, report: CalibrationReport) -> Any:
        if not access_ok:
            report.metrics["tree_nodes"] = 0
            return None
        res = adapter.get_accessibility_tree(int(window.window_id), pid=window.pid)
        if not res.ok or res.value is None:
            report.warnings.append("arbol de accesibilidad no disponible: %s" % res.error)
            report.metrics["tree_nodes"] = 0
            return None
        tree = res.value
        report.metrics["tree_nodes"] = len(tree.nodes)
        report.metrics["tree_truncated"] = bool(tree.truncated)
        report.metrics["tree_source"] = tree.source
        report.metrics["tree_hash"] = tree.structure_hash()
        if tree.error:
            report.warnings.append("arbol de accesibilidad parcial: %s" % tree.error)
        return tree

    def _stage_capture(
        self, adapter: Any, window: WindowInfo, capture_ok: bool, ctx: _RunContext, report: CalibrationReport
    ) -> Tuple[Any, Optional[str]]:
        if not capture_ok:
            return None, None
        res = adapter.capture_window(int(window.window_id))
        if not res.ok or res.value is None:
            report.warnings.append("captura de la ventana no disponible: %s" % res.error)
            return None, None
        capture = res.value
        report.metrics["capture"] = {
            "backend": capture.backend,
            "pixel_width": capture.pixel_width,
            "pixel_height": capture.pixel_height,
            "pixels_per_unit_x": capture.pixels_per_unit_x,
            "pixels_per_unit_y": capture.pixels_per_unit_y,
        }
        path = capture.path if capture.path and os.path.exists(capture.path) else None
        if path is None and capture.image is not None:
            path = self._save_temp_png(capture, ctx)
        return capture, path

    @staticmethod
    def _save_temp_png(capture: Any, ctx: _RunContext) -> Optional[str]:
        """Guarda la captura en un PNG temporal que se borra en la limpieza."""
        try:
            import numpy as np
            from PIL import Image

            image = np.asarray(capture.image)
            channels = str(capture.channels or "").upper()
            if image.ndim == 3 and image.shape[2] >= 3:
                rgb = image[:, :, :3]
                if channels.startswith("BGR"):
                    rgb = rgb[:, :, ::-1]
                pil = Image.fromarray(np.ascontiguousarray(rgb))
            else:
                pil = Image.fromarray(image)
            fd, path = tempfile.mkstemp(prefix="jarvis_calib_", suffix=".png")
            os.close(fd)
            pil.save(path)
            ctx.temp_files.append(path)
            return path
        except Exception as exc:
            logger.warning("[CALIBRATION-PIPELINE] no se pudo guardar la captura temporal: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Deteccion y fusion
    # ------------------------------------------------------------------

    def _stage_detection(
        self,
        app_info: Dict[str, Any],
        tree: Any,
        capture: Any,
        image_path: Optional[str],
        window: WindowInfo,
        transformer: Any,
        report: CalibrationReport,
    ) -> Tuple[List[Any], Any]:
        from src.eyes.detection.visual_ui_detector_fusion import (
            SOURCE_OMNIPARSER,
            SOURCE_PADDLEOCR,
            SOURCE_QWEN3VL,
            SOURCE_UIA,
        )
        from src.hands.calibration.coordinate_spaces import CoordinateSpace

        work_space = CoordinateSpace["FRAME_PIXELS"] if capture is not None else CoordinateSpace[
            str(getattr(self.adapter, "desktop_space", "DESKTOP_PIXELS"))
        ]
        candidates: List[Any] = []
        counts: Dict[str, int] = {}
        detectors: Dict[str, Any] = {}

        if tree is not None:
            access = self._accessibility_candidates(tree, window, transformer, work_space)
            candidates.extend(access)
            counts[SOURCE_UIA] = len(access)
            detectors[SOURCE_UIA] = {"source": tree.source, "status": "used"}

        accessible_actionable = sum(
            1 for c in candidates
            if (_get(c, "raw", {}) or {}).get("is_enabled")
            and ((_get(c, "raw", {}) or {}).get("actions") or (_get(c, "raw", {}) or {}).get("patterns"))
        )
        if self.visual_detectors == "never":
            run_visual, visual_reason = False, "desactivada (visual_detectors=never)"
        elif self.visual_detectors == "always":
            run_visual, visual_reason = True, "siempre (visual_detectors=always)"
        elif tree is None:
            run_visual, visual_reason = True, "sin arbol de accesibilidad"
        elif accessible_actionable < self.min_accessible_controls:
            run_visual, visual_reason = True, "accesibilidad insuficiente (%d controles accionables < %d)" % (
                accessible_actionable, self.min_accessible_controls)
        else:
            run_visual, visual_reason = False, "accesibilidad suficiente (%d controles accionables)" % accessible_actionable
        report.metrics["visual_detection"] = {
            "mode": self.visual_detectors,
            "used": bool(run_visual and capture is not None and image_path),
            "reason": visual_reason,
            "accessible_actionable": accessible_actionable,
        }

        if run_visual and capture is not None and image_path:
            manifest = None
            if self.use_optional_detectors:
                try:
                    manifest = self._detector_manifest()
                except Exception as exc:
                    report.warnings.append("manifiesto de detectores no disponible: %s" % exc)
            available = set(manifest.available_sources()) if manifest is not None else set()
            for source in ("qwen3vl", "omniparser", "paddleocr"):
                entry = self._manifest_entry(manifest, source)
                detectors[source] = {
                    "status": _get(entry, "status", "no_comprobado"),
                    "version": _get(entry, "version", ""),
                    "model": _get(entry, "model", ""),
                }
            if self._manifest_has(available, "qwen3vl"):
                found = self._qwen_candidates(app_info["name"], capture, image_path, window, report)
                candidates.extend(found)
                counts[SOURCE_QWEN3VL] = len(found)
            if self._manifest_has(available, "omniparser"):
                found = self._omniparser_candidates(manifest, image_path, window, report)
                candidates.extend(found)
                counts[SOURCE_OMNIPARSER] = len(found)
            if self._manifest_has(available, "paddleocr"):
                found = self._paddleocr_candidates(manifest, image_path, window, report)
                candidates.extend(found)
                counts[SOURCE_PADDLEOCR] = len(found)

        report.metrics["candidates_by_source"] = counts
        report.metrics["detectors"] = detectors
        report.metrics["work_space"] = getattr(work_space, "name", str(work_space))
        if not candidates:
            raise _StageFailure(STAGE_DETECTION, "ningun detector produjo candidatos")
        return candidates, work_space

    @staticmethod
    def _manifest_has(available: set, prefix: str) -> bool:
        return any(str(s).startswith(prefix) for s in available)

    @staticmethod
    def _manifest_entry(manifest: Any, prefix: str) -> Any:
        if manifest is None:
            return None
        for source, entry in (getattr(manifest, "entries", {}) or {}).items():
            if str(source).startswith(prefix):
                return entry
        return None

    def _accessibility_candidates(self, tree: Any, window: WindowInfo, transformer: Any, work_space: Any) -> List[Any]:
        from src.core.ui_element_model import UIElementData
        from src.eyes.detection.visual_ui_detector_fusion import SOURCE_UIA, DetectedCandidate
        from src.hands.calibration.coordinate_spaces import CoordinateSpace, SpaceBox

        desktop_space = CoordinateSpace[str(tree.coordinate_space or self.adapter.desktop_space)]
        window_rect = window.client_bounds or window.frame_bounds or window.bounds
        result = []
        for node in tree.nodes:
            if node.depth == 0 or node.bbox is None or not node.bbox.is_valid():
                continue
            # Contenedores que cubren casi toda la ventana no son controles.
            if window_rect is not None and window_rect.area > 0 and node.bbox.area >= 0.9 * window_rect.area:
                continue
            try:
                box = transformer.transform_box(SpaceBox.from_rect(node.bbox, desktop_space), work_space)
            except Exception as exc:
                logger.debug("[CALIBRATION-PIPELINE] nodo %s sin transformacion: %s", node.node_id, exc)
                continue
            bbox = [int(round(box.left)), int(round(box.top)), int(round(box.right)), int(round(box.bottom))]
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            center = [int(round((bbox[0] + bbox[2]) / 2.0)), int(round((bbox[1] + bbox[3]) / 2.0))]
            element = UIElementData(
                name=node.name or node.identifier or node.native_role,
                type=node.control_type,
                text=node.value,
                bbox=bbox,
                center=center,
                # La fusion usa ``interactive`` del candidato UIA como "habilitado".
                interactive=bool(node.enabled),
                confidence=1.0,
            )
            result.append(DetectedCandidate(
                source=SOURCE_UIA,
                element=element,
                confidence=1.0,
                bbox=bbox,
                center=center,
                screen=0,
                window_handle=int(window.window_id),
                process_id=int(window.pid),
                raw={
                    "patterns": node.equivalent_patterns,
                    "is_enabled": node.enabled,
                    "visible": node.visible,
                    "is_offscreen": node.offscreen,
                    "name": node.name,
                    "automation_id": node.identifier,
                    "native_role": node.native_role,
                    "node_id": node.node_id,
                    "actions": list(node.actions),
                    "accessibility_source": node.source,
                    "framework": node.framework,
                },
            ))
        return result

    def _qwen_candidates(
        self, app_name: str, capture: Any, image_path: str, window: WindowInfo, report: CalibrationReport
    ) -> List[Any]:
        """Candidatos visuales de Qwen3-VL reutilizando el contrato del calibrador universal
        (prompt, parseo y caja normalizada 0..1000 -> pixeles de la captura)."""
        from src.core.ui_element_model import UIElementData, normalize_element_type
        from src.eyes.detection.visual_ui_detector_fusion import SOURCE_QWEN3VL, DetectedCandidate

        started = time.monotonic()
        qwen_metrics: Dict[str, Any] = {}
        report.metrics["qwen3vl"] = qwen_metrics
        try:
            calibrator = self._vision_calibrator()
            try:
                prompt = calibrator._build_prompt(app_name, max_elements=self.vision_max_elements)
            except TypeError:
                prompt = calibrator._build_prompt(app_name)
            qwen_path = self._downscaled_copy(image_path, self.vision_max_side, qwen_metrics)
            try:
                raw = calibrator.vision.analyze_image(
                    str(qwen_path), prompt,
                    timeout=self.vision_timeout,
                    num_predict=max(1024, 60 * self.vision_max_elements + 400),
                )
            except TypeError:
                # Implementaciones de vision sin parametro de espera.
                raw = calibrator.vision.analyze_image(str(qwen_path), prompt)
            parsed = calibrator._parse_response(str(raw or "")) if raw else None
        except Exception as exc:
            qwen_metrics["seconds"] = round(time.monotonic() - started, 3)
            report.warnings.append("Qwen3-VL no disponible: %s" % exc)
            return []
        finally:
            if "qwen_path" in locals() and qwen_path != image_path:
                try:
                    os.unlink(str(qwen_path))
                except OSError as exc:
                    logger.debug("[CALIBRATION-PIPELINE] copia para Qwen3-VL no borrada: %s", exc)
        qwen_metrics["seconds"] = round(time.monotonic() - started, 3)
        if isinstance(raw, str) and raw.startswith("ERROR:"):
            report.warnings.append("Qwen3-VL no disponible: %s" % raw[len("ERROR:"):].strip()[:300])
            return []
        if not isinstance(parsed, dict) or not isinstance(parsed.get("elements"), list):
            report.warnings.append("Qwen3-VL devolvio una respuesta no interpretable")
            return []
        qwen_metrics["elements"] = len(parsed["elements"])
        if parsed.get("truncated"):
            qwen_metrics["truncated"] = True
            report.warnings.append(
                "Qwen3-VL corto la respuesta; se usan los %d elementos completos" % len(parsed["elements"])
            )
        width, height = int(capture.pixel_width), int(capture.pixel_height)
        result = []
        for raw_element in parsed["elements"]:
            if not isinstance(raw_element, dict) or raw_element.get("interactive", True) is False:
                continue
            confidence = calibrator._normalize_confidence(raw_element.get("confidence"))
            ok, _ = calibrator.policy.can_calibrate_element(str(raw_element.get("type", "other") or "other"), confidence)
            if not ok:
                continue
            image_bbox = calibrator._extract_image_bbox(raw_element, width, height)
            if image_bbox is None:
                continue
            bbox = [int(round(v)) for v in image_bbox]
            name = calibrator._normalize_element_name(
                raw_element.get("name") or raw_element.get("text") or raw_element.get("description")
            )
            if not name:
                continue
            center = [int(round((bbox[0] + bbox[2]) / 2.0)), int(round((bbox[1] + bbox[3]) / 2.0))]
            element = UIElementData(
                name=name,
                type=normalize_element_type(raw_element.get("type")),
                text=str(raw_element.get("text", "") or ""),
                description=str(raw_element.get("description", "") or ""),
                bbox=bbox,
                center=center,
                interactive=True,
                confidence=confidence,
            )
            result.append(DetectedCandidate(
                source=SOURCE_QWEN3VL,
                element=element,
                confidence=confidence,
                bbox=bbox,
                center=center,
                screen=0,
                window_handle=int(window.window_id),
                process_id=int(window.pid),
                raw={"name": name, "type": raw_element.get("type"), "model": getattr(calibrator, "MODEL", "")},
            ))
        return result

    @staticmethod
    def _downscaled_copy(image_path: str, max_side: int, metrics: Dict[str, Any]) -> str:
        """Copia temporal de la captura con el lado mayor <= ``max_side``.

        Devuelve la ruta original si ya cabe o si no se puede reducir. La
        copia la borra quien la pide.
        """
        try:
            from PIL import Image

            with Image.open(image_path) as image:
                width, height = image.size
                metrics["source_size"] = [int(width), int(height)]
                longest = max(width, height)
                if max_side <= 0 or longest <= max_side:
                    metrics["sent_size"] = [int(width), int(height)]
                    return image_path
                scale = float(max_side) / float(longest)
                size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
                reduced = image.convert("RGB").resize(size, Image.LANCZOS)
            fd, path = tempfile.mkstemp(prefix="jarvis_calib_qwen_", suffix=".png")
            os.close(fd)
            reduced.save(path)
            metrics["sent_size"] = [size[0], size[1]]
            return path
        except Exception as exc:
            logger.warning("[CALIBRATION-PIPELINE] no se pudo reducir la captura para Qwen3-VL: %s", exc)
            return image_path

    def _omniparser_candidates(self, manifest: Any, image_path: str, window: WindowInfo, report: CalibrationReport) -> List[Any]:
        from src.eyes.detection.visual_ui_detector_fusion import SOURCE_OMNIPARSER, DetectedCandidate

        entry = self._manifest_entry(manifest, "omniparser")
        try:
            from src.hands.detection.detector_manifest import obtener_adaptador_omniparser

            adapter = obtener_adaptador_omniparser(
                model_path=_get(entry, "weight_path"), device=_get(entry, "device", None)
            )
            regions = adapter.detect(image_path, screen=0)
        except Exception as exc:
            report.warnings.append("OmniParser no disponible: %s" % exc)
            return []
        result = []
        for region in regions:
            bbox = [int(v) for v in region.bbox]
            result.append(DetectedCandidate(
                source=SOURCE_OMNIPARSER,
                element=region.to_ui_element_data(),
                confidence=float(region.confidence),
                bbox=bbox,
                center=[(bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2],
                screen=0,
                window_handle=int(window.window_id),
                process_id=int(window.pid),
                raw=region.to_dict(),
            ))
        return result

    def _paddleocr_candidates(self, manifest: Any, image_path: str, window: WindowInfo, report: CalibrationReport) -> List[Any]:
        from src.core.ui_element_model import UIElementData
        from src.eyes.detection.visual_ui_detector_fusion import SOURCE_PADDLEOCR, DetectedCandidate

        entry = self._manifest_entry(manifest, "paddleocr")
        params = _get(entry, "parameters", {}) or {}
        try:
            from src.hands.detection.detector_manifest import obtener_adaptador_paddleocr

            device = _get(entry, "device", None)
            adapter = obtener_adaptador_paddleocr(
                model_dir=_get(entry, "weight_path"),
                rec_model_dir=params.get("rec_model_dir") if isinstance(params, dict) else None,
                device=device,
                use_gpu=(device == "cuda"),
            )
            regions = adapter.detect(image_path, screen=0)
        except Exception as exc:
            report.warnings.append("PaddleOCR no disponible: %s" % exc)
            return []
        result = []
        for region in regions:
            bbox = [int(v) for v in region.bbox]
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1] or not str(region.text or "").strip():
                continue
            center = [(bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2]
            result.append(DetectedCandidate(
                source=SOURCE_PADDLEOCR,
                element=UIElementData(
                    name=str(region.text), type="text", text=str(region.text), bbox=bbox,
                    center=center, interactive=False, confidence=float(region.confidence),
                ),
                confidence=float(region.confidence),
                bbox=bbox,
                center=center,
                screen=0,
                window_handle=int(window.window_id),
                process_id=int(window.pid),
                raw={"text": str(region.text)},
            ))
        return result

    def _stage_fusion(self, candidates: List[Any], image_path: Optional[str], window: WindowInfo, report: CalibrationReport) -> Any:
        try:
            fused = self.fusion.fuse(
                candidates,
                image_path=image_path,
                window_handle=int(window.window_id),
                process_id=int(window.pid),
                screen=0,
            )
        except Exception as exc:
            raise _StageFailure(STAGE_FUSION, "la fusion de detectores fallo: %s" % exc)
        if getattr(fused, "error", None):
            raise _StageFailure(STAGE_FUSION, "la fusion de detectores informo error: %s" % fused.error)
        report.metrics["fused"] = int(getattr(fused, "candidate_count", 0) or 0)
        report.metrics["duplicates_removed"] = int(getattr(fused, "duplicates_removed", 0) or 0)
        report.metrics["disagreements"] = int(getattr(fused, "disagreements_total", 0) or 0)
        report.metrics["sources_used"] = list(getattr(fused, "sources_used", []) or [])
        if not getattr(fused, "candidates", None):
            raise _StageFailure(STAGE_FUSION, "la fusion no produjo candidatos")
        return fused

    def _stage_quality_gate(
        self, fused: Any, window: WindowInfo, transformer: Any, work_space: Any, capture: Any, report: CalibrationReport
    ) -> Tuple[Any, Optional[Tuple[int, int, int, int]]]:
        from src.hands.calibration.coordinate_spaces import CoordinateSpace, SpaceBox

        desktop_space = CoordinateSpace[str(self.adapter.desktop_space)]
        window_rect_desktop = window.client_bounds or window.frame_bounds or window.bounds
        window_rect_work = None
        if window_rect_desktop is not None:
            try:
                box = transformer.transform_box(SpaceBox.from_rect(window_rect_desktop, desktop_space), work_space)
                window_rect_work = (
                    int(round(box.left)), int(round(box.top)), int(round(box.right)), int(round(box.bottom))
                )
            except Exception as exc:
                raise _StageFailure(STAGE_QUALITY_GATE, "no se pudo expresar la ventana en el espacio de trabajo: %s" % exc)
        image_rect = (0, 0, int(capture.pixel_width), int(capture.pixel_height)) if capture is not None else None
        try:
            result = self.gate.evaluate(list(fused.candidates), window_rect_work, image_rect=image_rect)
        except Exception as exc:
            raise _StageFailure(STAGE_QUALITY_GATE, "la puerta de calidad fallo: %s" % exc)
        accepted = list(_get(result, "accepted", []) or [])
        rejected = list(_get(result, "rejected", []) or [])
        detected_only = list(_get(result, "detected_not_actionable", []) or [])
        detected_ids = {id(c) for c in detected_only}
        report.metrics["gate_accepted"] = len(accepted)
        report.metrics["gate_rejected"] = len(rejected)
        report.metrics["gate_detected_not_actionable"] = len(detected_only)
        report.metrics["thresholds_fingerprint"] = str(_get(result, "thresholds_fingerprint", "") or "")
        for item in rejected:
            cand, reasons = (item[0], item[1]) if isinstance(item, (list, tuple)) and len(item) >= 2 else (item, [])
            if id(cand) in detected_ids:
                # Se conserva como definicion logica (CANDIDATO) en la etapa siguiente.
                continue
            report.elements.append(ElementReport(
                control_id=self._control_id(cand),
                name=str(_get(cand, "name", "") or ""),
                sources=[ev.source for ev in (_get(cand, "sources", []) or [])],
                identity=self._identity(cand),
                control_type=str(_get(cand, "type", "") or ""),
                interaction_capability=str(_to_plain(_get(cand, "classification", "")) or ""),
                coordinate_space=getattr(work_space, "name", str(work_space)),
                validity="BLOQUEADO",
                failure_reason="; ".join(str(r) for r in (reasons or [])) or "rechazado por la puerta de calidad",
            ))
        if not accepted:
            raise _StageFailure(
                STAGE_QUALITY_GATE,
                "ningun control accionable supero la puerta de calidad (%d detectados sin accion demostrada)"
                % len(detected_only),
            )
        return result, window_rect_work

    # ------------------------------------------------------------------
    # Transformacion, punto seguro y verificacion del puntero
    # ------------------------------------------------------------------

    @staticmethod
    def _identity(candidate: Any) -> Dict[str, Any]:
        identity: Dict[str, Any] = {"canonical_id": _get(candidate, "canonical_id", "")}
        for ev in _get(candidate, "sources", []) or []:
            raw = getattr(ev, "raw", {}) or {}
            if getattr(ev, "source", "") == "uia":
                identity["identifier"] = raw.get("automation_id", "")
                identity["native_role"] = raw.get("native_role", "")
                identity["accessibility_source"] = raw.get("accessibility_source", "")
                identity["actions"] = list(raw.get("actions", []) or [])
        return identity

    @staticmethod
    def _control_id(candidate: Any) -> str:
        identity = UICalibrationPipeline._identity(candidate)
        if identity.get("identifier"):
            base = "id:%s" % identity["identifier"]
        else:
            base = "%s:%s" % (_get(candidate, "type", "element"), _app_key(_get(candidate, "name", "")) or "sin_nombre")
        role = identity.get("native_role") or ""
        return "%s@%s" % (base, role) if role else base

    @classmethod
    def _unique_control_ids(cls, transformed: List[Tuple[Any, Any, Any, Any]]) -> List[str]:
        """``control_id`` unico por control del perfil.

        Dos controles distintos pueden dar el mismo id base: textos de OCR
        repetidos ("0" en la pantalla y en el boton de la Calculadora),
        controles sin nombre o sin identificador de accesibilidad. El perfil
        exige ids unicos (son la clave de puntos y cajas). Los repetidos
        reciben ``#1``, ``#2``... en orden de lectura (arriba-abajo,
        izquierda-derecha), estable mientras la disposicion de la ventana no
        cambie. Un id que no se repite se conserva tal cual.
        """
        bases = [cls._control_id(item[0]) for item in transformed]
        groups: Dict[str, List[int]] = {}
        for index, base in enumerate(bases):
            groups.setdefault(base, []).append(index)
        result = list(bases)
        taken = set(bases)
        for base, indexes in groups.items():
            if len(indexes) < 2:
                continue
            ordered = sorted(
                indexes,
                key=lambda i: (round(float(transformed[i][1].top)), round(float(transformed[i][1].left)), i),
            )
            ordinal = 0
            for i in ordered:
                ordinal += 1
                candidate_id = "%s#%d" % (base, ordinal)
                while candidate_id in taken:
                    ordinal += 1
                    candidate_id = "%s#%d" % (base, ordinal)
                taken.add(candidate_id)
                result[i] = candidate_id
        return result

    @staticmethod
    def _gate_key(candidate: Any) -> str:
        return str(
            _get(candidate, "canonical_id", None)
            or _get(candidate, "node_id", None)
            or _get(candidate, "name", None)
            or "desconocido"
        )

    def _assessment_for(self, gate_result: Any, candidate: Any) -> Any:
        assessments = _get(gate_result, "assessments")
        if isinstance(assessments, dict):
            return assessments.get(self._gate_key(candidate))
        return None

    def _decision_for(self, gate_result: Any, candidate: Any) -> Any:
        decisions = _get(gate_result, "decisions")
        if isinstance(decisions, dict):
            return decisions.get(self._gate_key(candidate))
        return None

    def _stage_transform_and_verify(
        self,
        app_info: Dict[str, Any],
        gate_result: Any,
        transformer: Any,
        work_space: Any,
        window: WindowInfo,
        display: DisplayInfo,
        snapshot: Any,
        ctx: _RunContext,
        report: CalibrationReport,
    ) -> List[Any]:
        from src.core.ui_element_model import ElementClassification
        from src.hands.calibration.calibration_profile_storage import CalibratedControlRecord, CalibrationState
        from src.hands.calibration.coordinate_spaces import CoordinateSpace, SpaceBox, compute_safe_point
        from src.hands.detection.calibration_quality_gate import decide_actionability, verify_before_action

        adapter = self.adapter
        desktop_space = CoordinateSpace[str(adapter.desktop_space)]
        accepted = list(_get(gate_result, "accepted", []) or [])
        detected_only = list(_get(gate_result, "detected_not_actionable", []) or [])
        accepted_ids = {id(c) for c in accepted}

        # Puntero inicial para restaurarlo al terminar.
        try:
            pos = adapter.get_pointer_position()
            if pos.ok and pos.value is not None:
                ctx.initial_pointer = (float(pos.value.x), float(pos.value.y))
        except Exception as exc:
            logger.debug("[CALIBRATION-PIPELINE] posicion inicial del puntero no disponible: %s", exc)

        transformed: List[Tuple[Any, Any, Any, Any]] = []
        for cand in accepted + detected_only:
            bbox = _get(cand, "bbox")
            try:
                work_box = SpaceBox(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]), work_space)
                desktop_box = transformer.transform_box(work_box, desktop_space)
                client_box = transformer.transform_box(work_box, CoordinateSpace["WINDOW_CLIENT"])
                norm_box = transformer.transform_box(work_box, CoordinateSpace["CLIENT_NORMALIZED"])
            except Exception as exc:
                report.elements.append(ElementReport(
                    control_id=self._control_id(cand), name=str(_get(cand, "name", "") or ""),
                    identity=self._identity(cand), validity="BLOQUEADO",
                    failure_reason="transformacion de coordenadas no verificable: %s" % exc,
                ))
                continue
            transformed.append((cand, work_box, desktop_box, (client_box, norm_box)))

        records: List[Any] = []
        checks_done = 0
        pointer_ok_count = 0
        all_desktop_boxes = [t[2] for t in transformed]
        detector_versions = {
            str(k): str(_get(v, "version", "") or "")
            for k, v in (report.metrics.get("detectors") or {}).items()
        }
        unique_ids = self._unique_control_ids(transformed)
        for index, (cand, work_box, desktop_box, (client_box, norm_box)) in enumerate(transformed):
            control_id = unique_ids[index]
            sources = [ev.source for ev in (_get(cand, "sources", []) or [])]
            assessment = self._assessment_for(gate_result, cand)
            decision = self._decision_for(gate_result, cand)
            if decision is None and assessment is not None:
                try:
                    decision = decide_actionability(cand, assessment)
                except Exception as exc:
                    logger.debug("[CALIBRATION-PIPELINE] decide_actionability fallo para %s: %s", control_id, exc)
            is_accepted = id(cand) in accepted_ids
            classification = _get(cand, "classification")
            accessibility_actionable = (
                is_accepted
                and "uia" in sources
                and classification == ElementClassification.UIA_ACTIONABLE
                and bool(_get(decision, "actionable", True))
            )

            reasons: List[str] = []
            pointer_result = None
            neighbors = [b for b in all_desktop_boxes if b is not desktop_box]
            safe_point = None
            try:
                safe_point = compute_safe_point(desktop_box, None, neighbors)
            except Exception as exc:
                reasons.append("punto seguro no calculable: %s" % exc)
            if safe_point is None and not reasons:
                reasons.append("sin punto seguro dentro del control")

            if not is_accepted:
                # Detectado sin accion demostrada: definicion logica (CANDIDATO),
                # sin verificar puntero ni habilitar acciones.
                safe_point_check = False
            else:
                safe_point_check = True
            if safe_point is not None and safe_point_check and checks_done < self.max_pointer_checks:
                # Entre la deteccion y aqui pasan etapas lentas (Qwen3-VL) en
                # las que otra ventana (consola, IDE) puede tomar el primer
                # plano. Antes de mover el puntero la ventana de prueba debe
                # tener el foco (regla de entrada sobre la ventana verificada):
                # si lo perdio se reactiva UNA vez y se deja constancia de que
                # ventana lo tenia; despues `verify_before_action` sigue
                # comprobando foco, geometria, monitor e identidad, de modo que
                # un cambio real (ventana movida, escala, PID) sigue bloqueando.
                if not adapter.is_foreground(int(window.window_id)):
                    fg_res = adapter.get_foreground_window()
                    fg_info = fg_res.value if (fg_res.ok and fg_res.value is not None) else None
                    quien = (
                        "%s (pid %s)" % (fg_info.app_identity or fg_info.title or "?", fg_info.pid)
                        if fg_info is not None else "desconocida"
                    )
                    report.warnings.append(
                        "la ventana de prueba perdio el foco antes de verificar el puntero; "
                        "lo tenia: %s; se reactiva" % quien
                    )
                    focus_log = report.metrics.setdefault("focus_restored", [])
                    focus_log.append({
                        "stage": STAGE_POINTER,
                        "foreground_app": fg_info.app_identity if fg_info is not None else None,
                        "foreground_pid": fg_info.pid if fg_info is not None else None,
                    })
                    res_act = adapter.activate_window(int(window.window_id))
                    if not res_act.ok:
                        raise _StageFailure(
                            STAGE_POINTER,
                            "no se pudo reactivar la ventana antes de verificar el puntero "
                            "(foco en %s): %s" % (quien, res_act.error),
                        )
                    if not adapter.is_foreground(int(window.window_id)):
                        raise _StageFailure(
                            STAGE_POINTER,
                            "la ventana de prueba no recupero el primer plano (foco en %s)" % quien,
                        )
                drift = verify_before_action(snapshot, adapter)
                if _get(drift, "action", "proceed") != "proceed":
                    raise _StageFailure(
                        STAGE_POINTER,
                        "cambio entre deteccion y accion: %s" % ", ".join(_get(drift, "changes", []) or []),
                        action=_get(drift, "action"),
                    )
                try:
                    input_point = transformer.to_input_point(safe_point)
                    pointer_result = self.pointer_verifier.move_and_verify(
                        input_point,
                        int(window.window_id),
                        expected_pid=int(window.pid),
                        expected_box=desktop_box,
                    )
                    ctx.pointer_moved = True
                except Exception as exc:
                    reasons.append("verificacion del puntero fallo: %s" % exc)
                checks_done += 1
                if pointer_result is not None and not _get(pointer_result, "ok", False):
                    reasons.append(str(_get(pointer_result, "reason", "") or "puntero fuera de tolerancia"))
            elif safe_point is not None and safe_point_check:
                reasons.append("verificacion del puntero pendiente (limite de comprobaciones alcanzado)")

            pointer_verified = bool(pointer_result is not None and _get(pointer_result, "ok", False))
            if pointer_verified:
                pointer_ok_count += 1
            geometric_state = CalibrationState.VALIDADO if pointer_verified else CalibrationState.DETECTADO
            semantic_state = (
                CalibrationState.VALIDADO
                if ("uia" in sources or len(set(sources)) >= 2)
                else CalibrationState.CANDIDATO
            )
            action_state = CalibrationState.VALIDADO if accessibility_actionable else CalibrationState.CANDIDATO
            interaction_method = INTERACTION_ACCESSIBILITY if accessibility_actionable else INTERACTION_NONE
            if not accessibility_actionable:
                reasons.append("sin accion demostrada: candidato visual o control no accionable")

            safe_norm = None
            safe_input = None
            if safe_point is not None:
                try:
                    norm_point = transformer.transform_point(safe_point, CoordinateSpace["CLIENT_NORMALIZED"])
                    safe_norm = (float(norm_point.x), float(norm_point.y))
                    input_point = transformer.to_input_point(safe_point)
                    safe_input = (float(input_point.x), float(input_point.y))
                except Exception as exc:
                    reasons.append("punto seguro sin normalizar: %s" % exc)

            confidences = {"detection": float(_get(cand, "merged_confidence", 0.0) or 0.0)}
            dims = _get(assessment, "dimensions", {}) or {}
            if isinstance(dims, dict):
                for name, dim in dims.items():
                    value = _get(dim, "value")
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        confidences[str(name)] = float(value)
            original_box = None
            for ev in _get(cand, "sources", []) or []:
                if getattr(ev, "bbox", None):
                    original_box = tuple(int(v) for v in ev.bbox)
                    break

            record = CalibratedControlRecord(
                control_id=control_id,
                app_id=app_info["app_key"],
                name=str(_get(cand, "name", "") or ""),
                control_type=str(_get(cand, "type", "") or ""),
                semantic_state=semantic_state,
                geometric_state=geometric_state,
                action_state=action_state,
                client_box_normalized=(
                    float(norm_box.left), float(norm_box.top), float(norm_box.right), float(norm_box.bottom)
                ),
                client_box_px=(
                    int(round(client_box.left)), int(round(client_box.top)),
                    int(round(client_box.right)), int(round(client_box.bottom)),
                ),
                safe_point_normalized=safe_norm,
                interaction_method=interaction_method,
                provenance=sources,
                detector_versions={k: v for k, v in detector_versions.items() if any(s.startswith(k[:4]) for s in sources)},
                original_box=original_box,
                refined_box=tuple(int(round(v)) for v in (work_box.left, work_box.top, work_box.right, work_box.bottom)),
                confidences=confidences,
                reasons=list(reasons),
                calibrated_at=_now_iso(),
            )
            records.append(record)

            precision: Dict[str, Any] = {}
            if pointer_result is not None:
                precision = {
                    "error_px": _get(pointer_result, "error_px"),
                    "error_ratio": _get(pointer_result, "error_ratio"),
                    "window_ok": _get(pointer_result, "window_ok"),
                    "element_ok": _get(pointer_result, "element_ok"),
                }
            validity = "VALIDADO" if pointer_verified else "DETECTADO"
            report.elements.append(ElementReport(
                control_id=control_id,
                name=record.name,
                sources=sources,
                identity=self._identity(cand),
                control_type=record.control_type,
                interaction_capability=str(_to_plain(classification) or ""),
                coordinate_space=getattr(desktop_space, "name", str(desktop_space)),
                display_id=display.display_id,
                scale_factor=display.scale_factor,
                precision=precision,
                allowed_action=interaction_method if pointer_verified else INTERACTION_NONE,
                validity=validity,
                failure_reason="; ".join(reasons),
            ))
            if pointer_verified and safe_input is not None:
                report.legacy_elements.append({
                    "name": record.name,
                    "type": record.control_type,
                    "center": [int(round(safe_input[0])), int(round(safe_input[1]))],
                    "bbox": [int(round(v)) for v in (desktop_box.left, desktop_box.top, desktop_box.right, desktop_box.bottom)],
                    "confidence": confidences["detection"],
                    "control_id": control_id,
                    "interaction_method": interaction_method,
                    "action_state": _to_plain(action_state),
                    "coordinate_space": getattr(desktop_space, "name", str(desktop_space)),
                    "display_id": display.display_id,
                })
        report.metrics["pointer_checks"] = checks_done
        report.metrics["pointer_verified"] = pointer_ok_count
        report.metrics["actionable"] = sum(
            1 for r in records if _to_plain(r.action_state) == _to_plain(CalibrationState.VALIDADO)
        )
        return records

    # ------------------------------------------------------------------
    # Persistencia y exploracion
    # ------------------------------------------------------------------

    def _stage_persist(
        self,
        app_info: Dict[str, Any],
        records: List[Any],
        window: WindowInfo,
        display: DisplayInfo,
        topology: Any,
        report: CalibrationReport,
    ) -> None:
        if not records:
            raise _StageFailure(STAGE_PERSISTENCE, "no hay controles que persistir")
        from src.hands.calibration.calibration_profile_storage import CalibrationProfile, CalibrationState
        from src.hands.calibration.calibration_validity import EnvironmentFingerprint, build_absolute_cache

        try:
            env = EnvironmentFingerprint.capture(
                self.adapter,
                int(window.window_id),
                machine_id=getattr(self.store, "machine_id", None),
                topology=topology,
            )
        except Exception as exc:
            raise _StageFailure(STAGE_PERSISTENCE, "no se pudo capturar la huella del entorno: %s" % exc)
        client = window.client_bounds or window.frame_bounds or window.bounds
        client_size = (int(round(client.width)), int(round(client.height))) if client is not None else (0, 0)
        any_validated = any(
            _to_plain(r.geometric_state) == _to_plain(CalibrationState.VALIDADO) for r in records
        )
        now = _now_iso()
        profile = CalibrationProfile(
            profile_id=uuid.uuid4().hex,
            machine_id=str(_get(env, "machine_id", "") or getattr(self.store, "machine_id", "") or ""),
            app_id=app_info["app_key"],
            topology_fingerprint=str(getattr(topology, "fingerprint", "") or ""),
            window_fingerprint=str(env.window_fingerprint()),
            display_id=display.display_id,
            scale_factor=float(display.scale_factor),
            dpi=int(display.dpi),
            display_pixel_size=(int(display.pixel_width), int(display.pixel_height)),
            orientation=display.orientation,
            window_state="maximized" if window.is_maximized else "normal",
            client_size=client_size,
            platform=report.platform,
            status=CalibrationState.VALIDADO if any_validated else CalibrationState.NO_VERIFICADO,
            created_at=now,
            updated_at=now,
            controls=records,
        )
        try:
            # Cache absoluta invalidable (puntos/cajas en el espacio del escritorio)
            # recalculada desde la geometria relativa del area cliente.
            profile.absolute_cache = build_absolute_cache(profile, window, env)
        except Exception as exc:
            report.warnings.append("cache absoluta no calculada: %s" % exc)
        try:
            report.profile_id = self.store.save_profile(profile)
        except Exception as exc:
            raise _StageFailure(STAGE_PERSISTENCE, "no se pudo guardar el perfil de calibracion: %s" % exc)
        report.metrics["profile_status"] = _to_plain(profile.status)

    def _reset_owned_app(self, app_info: Dict[str, Any], ctx: Any, display: Any, topology: Any) -> Any:
        """Callable de reinicio para la exploracion: SOLO para la app abierta
        por JARVIS. Cierra su ventana, la vuelve a abrir por el lanzador y la
        prepara igual (monitor, maximizada, primer plano)."""

        def _reset() -> Optional[Tuple[int, int]]:
            adapter = self.adapter
            current = ctx.window
            if current is not None:
                adapter.close_window(int(current.window_id))
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    res = adapter.get_window(int(current.window_id))
                    if not res.ok or res.value is None or not res.value.is_visible:
                        break
                    self._wait_event.wait(0.2)
            outcome = self.launcher.open(app_info["name"], timeout=self.launch_timeout)
            window = _get(outcome, "window")
            if not _get(outcome, "success", False) or window is None:
                return None
            prepared = self._stage_prepare_window(adapter, window, display, topology)
            ctx.window = prepared
            return int(prepared.window_id), int(prepared.pid)

        return _reset

    def _stage_exploration(
        self,
        app_info: Dict[str, Any],
        window: WindowInfo,
        depth: str,
        branch_ref: Any,
        access_ok: bool,
        report: CalibrationReport,
        ctx: Any = None,
        display: Any = None,
        topology: Any = None,
    ) -> None:
        """Exploracion en profundidad con clics verificados y mapa JSON.

        Pestanas, menus y elementos de navegacion se pulsan con el raton en el
        punto de su caja verificado antes del clic; cada transicion guarda la
        evidencia. Si la app la abrio JARVIS, las transiciones sin vuelta se
        resuelven reiniciandola. El mapa (estados con profundidad, elementos
        con coordenadas y transiciones) se guarda en
        ``data/ui_maps/<machine_id>/<app>.json`` y, en profundidad completa,
        se reproduce cada camino desde la raiz con las coordenadas guardadas.
        """
        from src.hands.calibration.ui_exploration import (
            DEFAULT_NAVIGATION_CONTAINERS,
            INTERACTION_CLICK,
            DeepUIExplorer,
            ExplorationSafetyPolicy,
            persist_state_map_logically,
        )

        if not access_ok:
            report.exploration = {"aborted": True, "abort_reason": "la exploracion requiere accesibilidad"}
            report.warnings.append("exploracion omitida: accesibilidad no disponible")
            return
        target_ref = None
        if depth == DEPTH_BRANCH:
            target_ref = dict(branch_ref) if isinstance(branch_ref, dict) else {"name": str(branch_ref)}
        owned = bool(getattr(ctx, "owned", False))
        reset = self._reset_owned_app(app_info, ctx, display, topology) if (owned and ctx is not None) else None
        explorer = DeepUIExplorer(
            adapter=self.adapter,
            policy=self.explorer_policy or ExplorationSafetyPolicy(
                allow_navigation=self.explore_navigation,
                navigation_containers=(
                    self.navigation_containers if self.navigation_containers is not None
                    else DEFAULT_NAVIGATION_CONTAINERS
                ),
            ),
            budget=self.explorer_budget,
            store=self._store,
            app_id=app_info["app_key"],
            interaction=INTERACTION_CLICK,
            reset_root=reset,
        )
        try:
            result = explorer.explore(
                int(window.window_id),
                int(window.pid),
                mode="full" if depth == DEPTH_DEEP else "branch",
                target_ref=target_ref,
            )
        except Exception as exc:
            report.exploration = {"aborted": True, "abort_reason": str(exc)}
            report.warnings.append("exploracion fallida: %s" % exc)
            return
        report.exploration = result.to_dict()
        if result.aborted:
            report.warnings.append("exploracion detenida: %s" % result.abort_reason)
        try:
            self._save_ui_map(app_info, result, explorer, ctx, display, depth, report)
        except Exception as exc:
            report.warnings.append("mapa de navegacion no guardado: %s" % exc)
        if result.state_map.states:
            saved, reason = persist_state_map_logically(app_info["app_key"], result.state_map)
            report.exploration["catalog_saved"] = saved
            if not saved:
                report.warnings.append("mapa de estados no guardado en el catalogo: %s" % reason)

    def _save_ui_map(
        self, app_info: Dict[str, Any], result: Any, explorer: Any, ctx: Any, display: Any, depth: str,
        report: CalibrationReport,
    ) -> None:
        from src.hands.calibration.ui_navigation_map import (
            UINavigator,
            build_navigation_map,
            save_navigation_map,
            verify_all_paths,
        )

        machine_id = str(getattr(self.store, "machine_id", "") or "")
        if not machine_id:
            from src.hands.inventory.system_inventory import generate_machine_id

            machine_id = generate_machine_id()
        current = getattr(ctx, "window", None) if ctx is not None else None
        data = build_navigation_map(result, app_info["app_key"], machine_id, window=current, display=display)
        if (
            depth == DEPTH_DEEP
            and explorer.reset_root is not None
            and current is not None
            and len(data["states"]) > 1
        ):
            # Prueba del mapa: cada camino desde la raiz con coordenadas guardadas.
            navigator = UINavigator(explorer, data, int(current.window_id), int(current.pid))
            verification = verify_all_paths(navigator)
            report.exploration["path_verification"] = {
                "ok": verification["ok"], "failed": verification["failed"],
            }
            if verification["failed"]:
                report.warnings.append(
                    "%d caminos del mapa no se pudieron reproducir con las coordenadas guardadas"
                    % verification["failed"]
                )
        path = save_navigation_map(data)
        report.exploration["ui_map_path"] = str(path)
        report.exploration["ui_map_states"] = len(data["states"])

    # ------------------------------------------------------------------
    # Navegadores y limpieza
    # ------------------------------------------------------------------

    @staticmethod
    def _is_browser(name: str) -> bool:
        key = _app_key(name)
        return any(b in key for b in BROWSER_KEYS)

    @staticmethod
    def _open_temporary_tab(adapter: Any, window: WindowInfo) -> bool:
        """Pestana temporal en un navegador del usuario (nunca toca sus pestanas)."""
        if not adapter.is_foreground(int(window.window_id)):
            return False
        res = adapter.press_keys(["primary_modifier", "t"])
        return bool(res.ok)

    def _cleanup(self, ctx: _RunContext, report: CalibrationReport) -> None:
        adapter = self._adapter
        for path in ctx.temp_files:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception as exc:
                logger.warning("[CALIBRATION-PIPELINE] no se pudo borrar la captura temporal: %s", exc)
        if adapter is None:
            return
        if ctx.pointer_moved and ctx.initial_pointer is not None:
            try:
                adapter.move_pointer(ctx.initial_pointer[0], ctx.initial_pointer[1])
            except Exception as exc:
                report.warnings.append("no se pudo restaurar el puntero: %s" % exc)
        window = ctx.window
        if window is None:
            return
        wid = int(window.window_id)
        if ctx.browser_tab_open:
            try:
                if adapter.is_foreground(wid):
                    adapter.press_keys(["primary_modifier", "w"])
                else:
                    report.warnings.append("la pestana temporal no se cerro: la ventana no estaba en primer plano")
            except Exception as exc:
                report.warnings.append("error cerrando la pestana temporal: %s" % exc)
        if ctx.owned:
            try:
                res = adapter.close_window(wid)
                if not res.ok:
                    report.warnings.append("no se pudo cerrar la ventana abierta por JARVIS: %s" % res.error)
            except Exception as exc:
                report.warnings.append("error cerrando la ventana abierta por JARVIS: %s" % exc)
            return
        original = ctx.original_window
        if original is None:
            return
        try:
            if ctx.original_display_id:
                current = adapter.get_window(wid)
                if current.ok and current.value is not None and current.value.display_id != ctx.original_display_id:
                    adapter.move_window_to_display(wid, ctx.original_display_id)
            if original.is_maximized:
                adapter.maximize_window(wid)
            else:
                adapter.restore_window(wid)
                if original.bounds is not None:
                    adapter.set_window_bounds(wid, original.bounds)
            if original.is_minimized:
                report.warnings.append(
                    "la ventana del usuario estaba minimizada; el contrato no expone minimizar y queda restaurada"
                )
        except Exception as exc:
            report.warnings.append("no se pudo restaurar el estado original de la ventana: %s" % exc)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _window_summary(window: WindowInfo) -> Dict[str, Any]:
        # Sin titulo: puede contener nombres de documentos del usuario.
        return {
            "window_id": int(window.window_id),
            "pid": int(window.pid),
            "app_identity": window.app_identity,
            "bounds": window.bounds.to_dict() if window.bounds else None,
            "client_bounds": window.client_bounds.to_dict() if window.client_bounds else None,
            "is_maximized": window.is_maximized,
            "is_foreground": window.is_foreground,
            "display_id": window.display_id,
            "scale_factor": window.scale_factor,
            "dpi": window.dpi,
        }

    @staticmethod
    def _redact(value: Any) -> Any:
        try:
            from src.core.operation_errors import redact_evidence

            return redact_evidence(value)
        except Exception as exc:
            logger.debug("[CALIBRATION-PIPELINE] redact_evidence no disponible: %s", exc)
            # Sin redactor no se publica evidencia que pueda contener rutas.
            return {"redacted": True}


# ============================================================================
# DELEGACION UNICA PARA CALIBRADORES HEREDADOS
# ============================================================================


def delegate_legacy_calibration(
    application_name: str,
    screen_number: Optional[int] = None,
    manager: Any = None,
) -> Dict[str, Any]:
    """Delega UNA sola vez en ``CalibrationManager.calibrate_application`` y
    devuelve un diccionario honesto (``success`` = resultado real).

    La usan los calibradores heredados (Edge, Firefox, ``apps/windows``) para no
    repetir calibraciones ni informar exito cuando la calibracion falla.
    """
    name = str(application_name or "").strip()
    if not name:
        return {"success": False, "application": "", "error": "nombre de aplicacion vacio"}
    try:
        if manager is None:
            from src.hands.calibration.calibration_manager import get_calibration_manager

            manager = get_calibration_manager()
        result = manager.calibrate_application(name, screen_number)
    except Exception as exc:
        logger.warning("[CALIBRATION-PIPELINE] calibracion heredada de %s fallo: %s", name, exc)
        return {"success": False, "application": name, "error": str(exc)}
    data = result.to_dict() if hasattr(result, "to_dict") else (dict(result) if isinstance(result, dict) else {})
    calibration_data = data.get("calibration_data") if isinstance(data.get("calibration_data"), dict) else {}
    elements = calibration_data.get("elements", []) if isinstance(calibration_data, dict) else []
    return {
        "success": bool(data.get("success", False)),
        "application": name,
        "monitor": int(data.get("screen_number", 0) or 0),
        "total_elements": int(data.get("elements_count", 0) or 0),
        "elements": list(elements) if isinstance(elements, list) else [],
        "error": data.get("error"),
        "calibration_data": calibration_data,
    }


__all__ = [
    "ElementReport",
    "CalibrationReport",
    "UICalibrationPipeline",
    "delegate_legacy_calibration",
    "INTERACTION_ACCESSIBILITY",
    "INTERACTION_POINTER",
    "INTERACTION_NONE",
    "DEPTH_SURFACE",
    "DEPTH_DEEP",
    "DEPTH_BRANCH",
    "POLICY_PRODUCT",
    "POLICY_TEST",
]
