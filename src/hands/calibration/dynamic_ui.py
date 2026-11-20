"""
Interfaces dinamicas: menus, popups, pestanas, scroll y virtualizacion.

Cubre (referencia de localizacion en el roadmap): 3.8.6.11.1 a 3.8.6.11.4.

* ``evaluate_presence``: distingue "presente en el arbol", "visible",
  "habilitado" e "interactuable ahora" (ventana en primer plano, caja dentro
  de un monitor y de la ventana, accion disponible).
* ``classify_dynamic_element`` y ``can_assign_coordinates``: menus, popups,
  tooltips, pestanas, dialogos, elementos de listas virtualizadas o con
  scroll. Nunca se asignan coordenadas a controles no renderizados; los
  transitorios solo admiten coordenadas de uso inmediato, no persistentes.
* ``navigation_for_element``: para un control fuera de pantalla o dentro de un
  contenedor cerrado devuelve una referencia semantica y la navegacion
  necesaria (scroll, expandir, seleccionar pestana, abrir menu, enfocar la
  ventana). Nunca devuelve un punto.
* ``frame_is_fresh``: limite de antiguedad de frame por tipo de accion.
* ``UIChangeDetector``: deteccion de cambios por comparacion de frames (y por
  eventos de accesibilidad notificados por el llamador), espera de
  estabilidad por sondeo con limite de tiempo (sin espera fija) y limite de
  CPU para el calculo de diferencias.
* ``ElementRelocator``: relee el arbol de accesibilidad de la ventana y
  relocaliza un elemento por identidad (identificador, nombre, tipo,
  ancestros). No reutiliza coordenadas antiguas.

Solo usa el contrato de plataforma (``src.desktop.platform_contract``) y el
modelo de accesibilidad comun; no llama APIs nativas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.core.ui_element_model import ElementClassification
from src.desktop.accessibility_model import (
    TRANSIENT_NATIVE_ROLES,
    AccessibilityNode,
    AccessibilityTree,
)
from src.desktop.platform_contract import (
    DesktopPlatformAdapter,
    DisplayInfo,
    Rect,
    WindowInfo,
)

logger = get_logger(__name__)


# ============================================================================
# PRESENCIA: EN EL ARBOL, VISIBLE, HABILITADO, INTERACTUABLE AHORA
# ============================================================================


@dataclass
class ElementPresence:
    """Estado de presencia de un elemento (cada nivel exige el anterior)."""

    in_tree: bool
    visible: bool
    enabled: bool
    interactable_now: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "in_tree": bool(self.in_tree),
            "visible": bool(self.visible),
            "enabled": bool(self.enabled),
            "interactable_now": bool(self.interactable_now),
            "reasons": list(self.reasons),
        }


def _display_list(displays: Any) -> List[DisplayInfo]:
    if displays is None:
        return []
    if hasattr(displays, "displays"):
        return list(getattr(displays, "displays") or [])
    return list(displays)


def evaluate_presence(
    node: Optional[AccessibilityNode],
    window: Optional[WindowInfo],
    displays: Any,
    window_is_foreground: bool,
) -> ElementPresence:
    """Evalua si un nodo esta presente, visible, habilitado e interactuable ahora.

    Argumentos:
        node: nodo normalizado (``None`` = no esta en el arbol).
        window: ventana que contiene el nodo (geometria en el mismo espacio).
        displays: lista de ``DisplayInfo`` o una topologia con ``displays``.
        window_is_foreground: si la ventana esta realmente en primer plano.
    """
    reasons: List[str] = []
    if node is None:
        return ElementPresence(False, False, False, False, ["no_presente_en_arbol"])

    visible = True
    box = node.bbox if (node.bbox is not None and node.bbox.is_valid()) else None
    if box is None:
        visible = False
        reasons.append("sin_geometria_renderizada")
    if node.offscreen:
        visible = False
        reasons.append("fuera_de_pantalla")
    if not node.visible:
        visible = False
        reasons.append("no_visible")
    if window is not None:
        if window.is_minimized:
            visible = False
            reasons.append("ventana_minimizada")
        if not window.is_visible:
            visible = False
            reasons.append("ventana_oculta")
    disp = _display_list(displays)
    fully_on_display = False
    if box is not None and disp:
        on_any = any(d.bounds.intersection_area(box) > 0 for d in disp)
        fully_on_display = any(d.bounds.contains_rect(box) for d in disp)
        if not on_any:
            visible = False
            reasons.append("fuera_de_todos_los_monitores")
        elif not fully_on_display:
            reasons.append("parcialmente_fuera_de_monitor")
    within_window = True
    if box is not None and window is not None:
        win_rect = window.frame_bounds or window.bounds
        if win_rect is not None:
            if win_rect.intersection_area(box) <= 0:
                visible = False
                within_window = False
                reasons.append("fuera_de_la_ventana")
            elif not win_rect.contains_rect(box):
                within_window = False
                reasons.append("recortado_por_la_ventana")

    enabled = bool(node.enabled)
    if not enabled:
        reasons.append("deshabilitado")

    interactable = visible and enabled
    if interactable and not window_is_foreground:
        interactable = False
        reasons.append("ventana_no_en_primer_plano")
    if interactable and not node.actions and node.classification() != ElementClassification.UIA_ACTIONABLE:
        interactable = False
        reasons.append("sin_accion_disponible")
    if interactable and disp and not fully_on_display:
        interactable = False
    if interactable and not within_window:
        interactable = False
    return ElementPresence(True, visible, enabled, interactable, reasons)


# ============================================================================
# CLASIFICACION DINAMICA Y ASIGNACION DE COORDENADAS
# ============================================================================

KIND_MENU = "menu"
KIND_POPUP = "popup"
KIND_TOOLTIP = "tooltip"
KIND_TAB = "tab"
KIND_DIALOG = "dialog"
KIND_LIST_ITEM = "list_item"
KIND_SCROLL_CONTAINER = "scroll_container"
KIND_STATIC = "static"

_MENU_ROLES = frozenset({"Menu", "MenuItem", "MenuBar", "AXMenu", "AXMenuItem", "AXMenuBar", "AXMenuBarItem"})
_POPUP_ROLES = frozenset({"AXPopover"})
_TOOLTIP_ROLES = frozenset({"ToolTip", "AXHelpTag"})
_TAB_ROLES = frozenset({"Tab", "TabItem", "AXTabGroup"})
_DIALOG_ROLES = frozenset({"AXDialog", "AXSheet"})
_LIST_ITEM_ROLES = frozenset({"ListItem", "TreeItem", "DataItem", "AXRow", "AXCell", "AXOutlineRow"})


def classify_dynamic_element(node: AccessibilityNode) -> str:
    """Tipo dinamico del elemento segun su rol nativo y sus acciones."""
    role = node.native_role
    subrole = str(node.raw.get("subrole", "") or "")
    if role in _TOOLTIP_ROLES:
        return KIND_TOOLTIP
    if role in _MENU_ROLES:
        return KIND_MENU
    if role in _POPUP_ROLES:
        return KIND_POPUP
    if role in _DIALOG_ROLES or subrole in ("AXDialog", "AXSystemDialog"):
        return KIND_DIALOG
    if role in _TAB_ROLES or (role == "AXRadioButton" and subrole == "AXTabButton"):
        return KIND_TAB
    if role in _LIST_ITEM_ROLES:
        return KIND_LIST_ITEM
    if "scroll" in node.actions and role not in _LIST_ITEM_ROLES:
        return KIND_SCROLL_CONTAINER
    return KIND_STATIC


def is_transient(node: AccessibilityNode) -> bool:
    """Menus desplegados, popups y tooltips: desaparecen sin accion del usuario."""
    return node.native_role in TRANSIENT_NATIVE_ROLES or classify_dynamic_element(node) in (
        KIND_TOOLTIP, KIND_POPUP,
    )


def can_assign_coordinates(
    node: AccessibilityNode, presence: ElementPresence, persistent: bool = False
) -> Tuple[bool, str]:
    """Decide si se pueden asignar coordenadas a un nodo.

    Nunca a un control no renderizado (no visible o fuera de pantalla). A un
    elemento transitorio solo para uso inmediato (``persistent=False``).
    """
    if not presence.in_tree:
        return False, "no presente en el arbol"
    if not presence.visible or node.bbox is None:
        return False, "control no renderizado: se devuelve referencia semantica y navegacion"
    if persistent and is_transient(node):
        return False, "elemento transitorio: sus coordenadas no se persisten"
    return True, "control renderizado"


# ============================================================================
# NAVEGACION HACIA ELEMENTOS NO VISIBLES (sin puntos ficticios)
# ============================================================================

NAV_SCROLL = "scroll"
NAV_EXPAND = "expand"
NAV_SELECT_TAB = "select_tab"
NAV_OPEN_MENU = "open_menu"
NAV_FOCUS_WINDOW = "focus_window"


@dataclass
class NavigationStep:
    """Paso de navegacion sobre un nodo identificado semanticamente."""

    action: str
    target_node_id: Optional[str]
    detail: str = ""
    target_ref: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target_node_id": self.target_node_id,
            "detail": self.detail,
            "target_ref": dict(self.target_ref),
        }


@dataclass
class NavigationHint:
    """Referencia semantica de un elemento y navegacion para hacerlo visible."""

    element_node_id: Optional[str]
    reachable: bool
    steps: List[NavigationStep] = field(default_factory=list)
    reason: str = ""
    element_ref: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_node_id": self.element_node_id,
            "reachable": bool(self.reachable),
            "steps": [s.to_dict() for s in self.steps],
            "reason": self.reason,
            "element_ref": dict(self.element_ref),
        }


def semantic_reference(node: AccessibilityNode, tree: Optional[AccessibilityTree] = None) -> Dict[str, Any]:
    """Referencia semantica estable de un nodo (sin coordenadas)."""
    ancestors: List[Dict[str, str]] = []
    if tree is not None:
        for anc in reversed(tree.ancestors_of(node.node_id)):
            ancestors.append({"native_role": anc.native_role, "name": anc.name, "identifier": anc.identifier})
    return {
        "identifier": node.identifier,
        "name": node.name,
        "control_type": node.control_type,
        "native_role": node.native_role,
        "ancestors": ancestors,
    }


def navigation_for_element(
    node: AccessibilityNode,
    tree: AccessibilityTree,
    window_is_foreground: Optional[bool] = None,
) -> NavigationHint:
    """Navegacion necesaria para que un elemento quede visible e interactuable.

    Recorre los ancestros desde la raiz: un menu cerrado se abre
    (``open_menu``), un contenedor plegable se expande (``expand``), una
    pestana no seleccionada se selecciona (``select_tab``) y un contenedor con
    scroll se desplaza (``scroll``). Si la ventana no esta en primer plano se
    antepone ``focus_window``. Nunca devuelve coordenadas.
    """
    ref = semantic_reference(node, tree)
    steps: List[NavigationStep] = []
    if window_is_foreground is False:
        steps.append(NavigationStep(NAV_FOCUS_WINDOW, None, "activar y verificar la ventana objetivo"))
    hidden = node.offscreen or not node.visible or node.bbox is None
    if not hidden:
        return NavigationHint(node.node_id, True, steps, "elemento ya visible", ref)

    for anc in reversed(tree.ancestors_of(node.node_id)):
        anc_ref = semantic_reference(anc, tree)
        kind = classify_dynamic_element(anc)
        if kind == KIND_MENU and ("expand" in anc.actions or "show_menu" in anc.actions or "invoke" in anc.actions):
            if anc.offscreen or not anc.visible or anc.native_role in ("MenuItem", "AXMenuItem", "AXMenuBarItem"):
                steps.append(NavigationStep(NAV_OPEN_MENU, anc.node_id, "abrir menu %s" % anc.name, anc_ref))
                continue
        if "expand" in anc.actions and kind != KIND_SCROLL_CONTAINER:
            steps.append(NavigationStep(NAV_EXPAND, anc.node_id, "expandir %s" % (anc.name or anc.native_role), anc_ref))
            continue
        if kind == KIND_TAB and "select" in anc.actions and anc.native_role in ("TabItem", "AXRadioButton"):
            steps.append(NavigationStep(NAV_SELECT_TAB, anc.node_id, "seleccionar pestana %s" % anc.name, anc_ref))
            continue
        if "scroll" in anc.actions:
            steps.append(NavigationStep(NAV_SCROLL, anc.node_id, "desplazar hasta el elemento", anc_ref))
    if "scroll" in node.actions and not any(s.action == NAV_SCROLL for s in steps):
        steps.append(NavigationStep(NAV_SCROLL, node.node_id, "scroll_into_view del propio elemento", ref))

    useful = [s for s in steps if s.action != NAV_FOCUS_WINDOW]
    if not useful:
        return NavigationHint(
            node.node_id, False, steps,
            "sin ruta de navegacion conocida: no se asignan coordenadas", ref,
        )
    return NavigationHint(node.node_id, True, steps, "navegacion semantica necesaria", ref)


# ============================================================================
# ANTIGUEDAD DE FRAME POR ACCION
# ============================================================================

# Politica configurable (segundos). No son medidas: limitan cuanto puede
# reutilizarse una captura antes de cada tipo de accion; la fixture puede
# ajustarlos. Una accion desconocida usa "default".
FRAME_MAX_AGE_SECONDS: Dict[str, float] = {
    "click": 2.0,
    "double_click": 2.0,
    "type": 2.0,
    "hover": 1.0,
    "scroll": 3.0,
    "expand": 2.0,
    "select": 2.0,
    "verify": 5.0,
    "calibrate": 5.0,
    "read": 10.0,
    "default": 2.0,
}


def frame_is_fresh(
    captured_at: Optional[float],
    action: str,
    now: Optional[float] = None,
    limits: Optional[Dict[str, float]] = None,
) -> bool:
    """True si un frame capturado en ``captured_at`` (monotonic) sigue vigente."""
    if captured_at is None:
        return False
    table = limits or FRAME_MAX_AGE_SECONDS
    limit = table.get(action, table.get("default", 2.0))
    current = time.monotonic() if now is None else float(now)
    age = current - float(captured_at)
    return 0.0 <= age <= float(limit)


# ============================================================================
# DETECCION DE CAMBIOS Y ESTABILIDAD
# ============================================================================

# Umbral de transicion de AdaptiveCapture (diferencia normalizada media).
DEFAULT_DIFF_THRESHOLD = 0.05


@dataclass
class StabilityResult:
    """Resultado de esperar a que la interfaz deje de cambiar."""

    stable: bool
    frames_observed: int
    elapsed_seconds: float
    last_diff: Optional[float]
    reason: str
    changes_observed: int = 0
    accessibility_events: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stable": bool(self.stable),
            "frames_observed": int(self.frames_observed),
            "elapsed_seconds": float(self.elapsed_seconds),
            "last_diff": self.last_diff,
            "reason": self.reason,
            "changes_observed": int(self.changes_observed),
            "accessibility_events": int(self.accessibility_events),
        }


def _frame_array(value: Any) -> Any:
    """Extrae el array de un frame (ndarray, FrameInfo o CaptureResult)."""
    if value is None:
        return None
    for attr in ("frame", "image"):
        inner = getattr(value, attr, None)
        if inner is not None:
            return inner
    return value if hasattr(value, "shape") else None


class UIChangeDetector:
    """Detecta cambios de interfaz comparando frames consecutivos.

    Argumentos:
        diff_threshold: diferencia normalizada media (0..1) a partir de la cual
            dos frames se consideran distintos. Por defecto, el umbral de
            transicion de ``AdaptiveCapture``.
        max_pixels: numero maximo de pixeles usados para comparar (se
            submuestrea con paso uniforme); acota el coste por frame.
        max_cpu_fraction: fraccion maxima del tiempo de pared dedicada a
            comparar frames durante ``wait_until_stable``; el intervalo de
            sondeo se alarga si el calculo es caro.
        min_poll_interval: intervalo minimo entre capturas al esperar.
        clock/sleeper: inyectables para pruebas deterministas.
    """

    def __init__(
        self,
        diff_threshold: float = DEFAULT_DIFF_THRESHOLD,
        max_pixels: int = 250_000,
        max_cpu_fraction: float = 0.25,
        min_poll_interval: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.diff_threshold = float(diff_threshold)
        self.max_pixels = max(1, int(max_pixels))
        self.max_cpu_fraction = min(1.0, max(0.01, float(max_cpu_fraction)))
        self.min_poll_interval = max(0.0, float(min_poll_interval))
        self._clock = clock
        self._sleep = sleeper
        self._previous: Any = None
        self._last_diff: Optional[float] = None
        self._last_compute_seconds = 0.0
        self._pending_events = 0
        self._events_total = 0

    def reset(self) -> None:
        self._previous = None
        self._last_diff = None
        self._pending_events = 0

    @property
    def last_diff(self) -> Optional[float]:
        return self._last_diff

    def notify_accessibility_event(self, kind: str = "") -> None:
        """Registra un evento de accesibilidad fiable (estructura/foco cambiado).

        El adaptador o el llamador lo invoca cuando dispone de eventos UIA/AX
        fiables; cualquier evento cuenta como cambio en la siguiente
        observacion.
        """
        self._pending_events += 1
        self._events_total += 1
        logger.debug("Evento de accesibilidad registrado: %s", kind)

    def _downsample(self, frame: Any) -> Any:
        try:
            height, width = int(frame.shape[0]), int(frame.shape[1])
        except Exception:
            return frame
        total = max(1, height * width)
        if total <= self.max_pixels:
            return frame
        step = int((total / float(self.max_pixels)) ** 0.5) + 1
        return frame[::step, ::step]

    def diff(self, a: Any, b: Any) -> float:
        """Diferencia normalizada media entre dos frames (1.0 si no son comparables)."""
        if a is None or b is None:
            return 1.0
        try:
            import numpy as np

            sa = self._downsample(a)
            sb = self._downsample(b)
            if getattr(sa, "shape", None) != getattr(sb, "shape", None):
                return 1.0
            return float(np.abs(sa.astype(np.float32) - sb.astype(np.float32)).mean() / 255.0)
        except Exception as exc:
            logger.debug("No se pudo comparar frames: %s", exc)
            return 1.0

    def observe(self, frame: Any, timestamp: Optional[float] = None) -> bool:
        """Registra un frame y devuelve True si hubo cambio respecto al anterior.

        El primer frame cuenta como cambio (no hay referencia). Un evento de
        accesibilidad pendiente tambien cuenta como cambio.
        """
        array = _frame_array(frame)
        start = self._clock()
        if self._previous is None or array is None:
            changed = True
            self._last_diff = None
        else:
            self._last_diff = self.diff(self._previous, array)
            changed = self._last_diff > self.diff_threshold
        self._last_compute_seconds = max(0.0, self._clock() - start)
        if self._pending_events:
            changed = True
            self._pending_events = 0
        if array is not None:
            self._previous = array
        return changed

    def _poll_interval(self) -> float:
        budget = self._last_compute_seconds / self.max_cpu_fraction
        return max(self.min_poll_interval, budget - self._last_compute_seconds)

    def wait_until_stable(
        self,
        capture_fn: Callable[[], Any],
        timeout: float,
        stable_frames: int = 3,
        tree_hash_fn: Optional[Callable[[], Optional[str]]] = None,
    ) -> StabilityResult:
        """Sondea capturas hasta ``stable_frames`` observaciones seguidas sin cambio.

        Sin espera fija: captura, compara y solo duerme el intervalo minimo
        que respeta el limite de CPU, hasta ``timeout``. Si ``tree_hash_fn``
        se da, el hash del arbol de accesibilidad tambien debe mantenerse.
        Un frame ``None`` no cuenta como estable.
        """
        self.reset()
        start = self._clock()
        events_before = self._events_total
        frames = 0
        changes = 0
        consecutive = 0
        previous_hash: Optional[str] = None
        reason = "tiempo agotado sin estabilidad"
        while True:
            elapsed = self._clock() - start
            if elapsed > float(timeout):
                break
            try:
                frame = capture_fn()
            except Exception as exc:
                logger.warning("Fallo de captura esperando estabilidad: %s", exc)
                frame = None
            array = _frame_array(frame)
            if array is None:
                consecutive = 0
                reason = "captura no disponible"
            else:
                frames += 1
                changed = self.observe(array)
                if tree_hash_fn is not None:
                    try:
                        current_hash = tree_hash_fn()
                    except Exception as exc:
                        logger.debug("No se pudo leer el hash del arbol: %s", exc)
                        current_hash = None
                    if current_hash is None or current_hash != previous_hash:
                        changed = True
                    previous_hash = current_hash
                if changed:
                    changes += 1
                    consecutive = 0
                else:
                    consecutive += 1
                    if consecutive >= max(1, int(stable_frames)) - 1 and frames >= int(stable_frames):
                        return StabilityResult(
                            True, frames, self._clock() - start, self._last_diff,
                            "interfaz estable", changes, self._events_total - events_before,
                        )
            remaining = float(timeout) - (self._clock() - start)
            if remaining <= 0:
                break
            self._sleep(min(remaining, self._poll_interval()))
        return StabilityResult(
            False, frames, self._clock() - start, self._last_diff, reason, changes,
            self._events_total - events_before,
        )


def adaptive_capture_fn(adaptive_capture: Any) -> Callable[[], Any]:
    """Adapta ``AdaptiveCapture.grab_adaptive`` a ``capture_fn`` de la espera.

    ``grab_adaptive`` no bloquea y devuelve ``None`` si aun no toca entregar;
    en ese caso se reutiliza el ultimo frame entregado (sin repetir captura).
    """
    def _capture() -> Any:
        info = adaptive_capture.grab_adaptive()
        if info is None:
            info = adaptive_capture.get_latest()
        return info.frame if info is not None else None

    return _capture


def adapter_capture_fn(adapter: DesktopPlatformAdapter, window_id: int) -> Callable[[], Any]:
    """``capture_fn`` que captura la ventana via el contrato de plataforma."""
    def _capture() -> Any:
        result = adapter.capture_window(int(window_id))
        if not result.ok or result.value is None:
            return None
        return result.value.image

    return _capture


# ============================================================================
# RELOCALIZACION POR IDENTIDAD
# ============================================================================


@dataclass
class RelocationResult:
    """Resultado de relocalizar un elemento en el arbol actual."""

    found: bool
    node: Optional[AccessibilityNode]
    reason: str
    tree_hash: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    navigation: Optional[NavigationHint] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "found": bool(self.found),
            "node": self.node.to_dict() if self.node else None,
            "reason": self.reason,
            "tree_hash": self.tree_hash,
            "candidates": list(self.candidates),
            "navigation": self.navigation.to_dict() if self.navigation else None,
        }


def _ancestor_score(node: AccessibilityNode, tree: AccessibilityTree, wanted: Sequence[Dict[str, Any]]) -> int:
    if not wanted:
        return 0
    actual = [
        (a.native_role, a.name.strip().lower(), a.identifier)
        for a in reversed(tree.ancestors_of(node.node_id))
    ]
    score = 0
    for w in wanted:
        key = (str(w.get("native_role", "") or ""), str(w.get("name", "") or "").strip().lower(),
               str(w.get("identifier", "") or ""))
        for a in actual:
            if (not key[0] or key[0] == a[0]) and (not key[1] or key[1] == a[1]) and (not key[2] or key[2] == a[2]):
                score += 1
                break
    return score


class ElementRelocator:
    """Relocaliza elementos releyendo el arbol de accesibilidad actual."""

    def __init__(self, adapter: Optional[DesktopPlatformAdapter] = None) -> None:
        self._adapter = adapter

    @property
    def adapter(self) -> DesktopPlatformAdapter:
        if self._adapter is None:
            from src.desktop.platform_contract import get_desktop_platform

            self._adapter = get_desktop_platform()
        return self._adapter

    def relocate(
        self,
        window_id: int,
        reference: Dict[str, Any],
        tree: Optional[AccessibilityTree] = None,
        pid: Optional[int] = None,
    ) -> RelocationResult:
        """Busca el elemento descrito por ``reference`` en el arbol actual.

        ``reference`` admite ``identifier``, ``name``, ``control_type``,
        ``native_role`` y ``ancestors`` (lista de dicts con ``native_role``,
        ``name``, ``identifier``). Cualquier coordenada de la referencia se
        ignora. Coincidencia: identificador exacto si existe; si no, nombre +
        tipo. Empates no resueltos por ancestros -> ambiguo (no se elige).
        """
        if tree is None:
            res = self.adapter.get_accessibility_tree(int(window_id), pid=pid)
            if not res.ok or res.value is None:
                code = res.error.code.value if res.error else "desconocido"
                return RelocationResult(False, None, "arbol de accesibilidad no disponible: %s" % code)
            tree = res.value
        tree_hash = tree.structure_hash() if hasattr(tree, "structure_hash") else None

        identifier = str(reference.get("identifier", "") or "")
        name = str(reference.get("name", "") or "").strip().lower()
        control_type = str(reference.get("control_type", "") or "")
        native_role = str(reference.get("native_role", "") or "")
        ancestors = list(reference.get("ancestors") or [])
        if not identifier and not name:
            return RelocationResult(False, None, "referencia sin identidad (identificador o nombre)", tree_hash)

        matches: List[AccessibilityNode] = []
        for node in tree.nodes:
            if identifier:
                if node.identifier != identifier:
                    continue
            elif node.name.strip().lower() != name:
                continue
            if control_type and node.control_type != control_type:
                continue
            if native_role and node.native_role != native_role:
                continue
            matches.append(node)

        if not matches:
            return RelocationResult(False, None, "elemento no encontrado en el arbol actual", tree_hash)
        if len(matches) > 1 and ancestors:
            scored = sorted(((_ancestor_score(n, tree, ancestors), n) for n in matches),
                            key=lambda item: item[0], reverse=True)
            best_score = scored[0][0]
            matches = [n for s, n in scored if s == best_score]
        if len(matches) > 1:
            return RelocationResult(
                False, None, "relocalizacion ambigua: %d candidatos" % len(matches), tree_hash,
                [n.node_id for n in matches],
            )
        node = matches[0]
        navigation = None
        if node.offscreen or not node.visible or node.bbox is None:
            navigation = navigation_for_element(node, tree)
        return RelocationResult(True, node, "elemento relocalizado por identidad", tree_hash, [node.node_id], navigation)


__all__ = [
    "ElementPresence",
    "evaluate_presence",
    "KIND_MENU",
    "KIND_POPUP",
    "KIND_TOOLTIP",
    "KIND_TAB",
    "KIND_DIALOG",
    "KIND_LIST_ITEM",
    "KIND_SCROLL_CONTAINER",
    "KIND_STATIC",
    "classify_dynamic_element",
    "is_transient",
    "can_assign_coordinates",
    "NAV_SCROLL",
    "NAV_EXPAND",
    "NAV_SELECT_TAB",
    "NAV_OPEN_MENU",
    "NAV_FOCUS_WINDOW",
    "NavigationStep",
    "NavigationHint",
    "semantic_reference",
    "navigation_for_element",
    "FRAME_MAX_AGE_SECONDS",
    "frame_is_fresh",
    "DEFAULT_DIFF_THRESHOLD",
    "StabilityResult",
    "UIChangeDetector",
    "adaptive_capture_fn",
    "adapter_capture_fn",
    "RelocationResult",
    "ElementRelocator",
]
