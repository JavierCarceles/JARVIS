"""
Exploracion profunda y segura de la interfaz de una aplicacion.

Recorre de forma acotada menus, submenus, pestanas y (opcionalmente) dialogos
no destructivos de la ventana de una aplicacion ya identificada, y construye un
mapa de estados UI reutilizable por el Planner (cubre 3.8.6.12.1-3.8.6.12.5).

Componentes:

* ``UIStateNode``, ``UITransition`` y ``UIStateMap``: mapa de estados. Un
  estado es la huella de las ventanas del proceso (ids) mas la firma logica de
  sus arboles de accesibilidad (rol, nombre, identificador, profundidad y
  estado), sin cajas ni coordenadas. Una transicion es ``accion -> estado
  resultante`` con su forma de volver (``collapse``, ``escape``,
  ``select_previous_tab``, ``close_opened_window``) y si la vuelta se verifico.
  ``to_logical_dict()`` es la persistencia logica para el catalogo (sin
  coordenadas); la geometria fisica de los controles se persiste en SQLite por
  ``machine_id`` mediante los perfiles de calibracion (no en este modulo).
* ``ExplorationSafetyPolicy``: decide si una accion de exploracion es segura.
  Solo admite ``expand``, ``select_tab`` y ``open_menu`` (y ``open_dialog``
  unicamente si se habilita explicitamente: elementos de menu cuyo texto acaba
  en puntos suspensivos). Rechaza cualquier control cuya etiqueta contenga una
  accion con efecto (guardar, enviar, borrar, eliminar, comprar, pagar,
  publicar, cerrar sesion, instalar, actualizar, formatear, salir, aceptar
  terminos... en espanol e ingles), controles sin etiqueta (semantica
  desconocida), iconos de cierre/papelera y cualquier accion de escritura
  (``set_value``, ``toggle``, ``type_text``). Ante la duda, NO.
* ``ExplorationBudget`` y ``ExplorationCheckpoint``: limites de profundidad,
  estados, tiempo y acciones; punto de control serializable para reanudar.
* ``DeepUIExplorer``: recorrido en anchura por niveles. Para explorar un
  estado reproduce la ruta desde el estado raiz, prueba cada accion segura de
  los elementos nuevos de ese estado, registra el estado resultante, vuelve al
  estado de partida y COMPRUEBA la vuelta. Si la vuelta falla o aparece algo
  inesperado, se detiene, cierra solo las ventanas abiertas durante la
  exploracion y registra el estado. Nunca fuerza el cierre de la aplicacion.

Profundidad bajo demanda: ``mode="full"`` recorre todo dentro del presupuesto
("calibra X a fondo"); ``mode="branch"`` busca solo la rama que hace visible un
elemento de referencia que necesita el Planner y se detiene al encontrarlo.

Todo el acceso al SO pasa por el contrato de escritorio
(``src.desktop.platform_contract``); este modulo no usa APIs nativas.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from src.core.log import get_logger
from src.desktop.accessibility_model import AccessibilityNode, AccessibilityTree

logger = get_logger(__name__)


# ============================================================================
# POLITICA DE SEGURIDAD
# ============================================================================

# Acciones de exploracion admitidas (nombres logicos de este modulo).
ACTION_EXPAND = "expand"
ACTION_SELECT_TAB = "select_tab"
ACTION_OPEN_MENU = "open_menu"
ACTION_OPEN_DIALOG = "open_dialog"

EXPLORATION_ACTIONS = frozenset({ACTION_EXPAND, ACTION_SELECT_TAB, ACTION_OPEN_MENU, ACTION_OPEN_DIALOG})

# Formas de volver al estado anterior.
RETURN_COLLAPSE = "collapse"
RETURN_ESCAPE = "escape"
RETURN_SELECT_PREVIOUS_TAB = "select_previous_tab"
RETURN_CLOSE_OPENED_WINDOW = "close_opened_window"

# Acciones que nunca se ejecutan durante la exploracion (escritura o efecto).
NEVER_ACTIONS = frozenset({"set_value", "toggle", "type_text", "scroll", "invoke_leaf"})

# Roles nativos de pestanas (UIA y AX).
TAB_ROLES = frozenset({"TabItem", "AXTab", "AXRadioButton"})

# Roles nativos que abren un menu o desplegable al activarlos.
MENU_OPENER_ROLES = frozenset({
    "MenuItem", "MenuBarItem", "SplitButton", "ComboBox",
    "AXMenuBarItem", "AXMenuButton", "AXPopUpButton", "AXMenuItem",
})

# Roles nativos de elementos de menu (posibles abridores de dialogo "...").
MENU_ITEM_ROLES = frozenset({"MenuItem", "AXMenuItem"})

# Terminos prohibidos. Se comparan tras normalizar (minusculas, sin acentos,
# sin puntuacion), por lo que "Cerrar sesion" con o sin tilde coinciden.
FORBIDDEN_TERMS_ES: Tuple[str, ...] = (
    "guardar", "guardar como", "enviar", "reenviar", "responder", "borrar",
    "eliminar", "suprimir", "quitar", "vaciar", "limpiar", "descartar",
    "comprar", "compra", "pagar", "pago", "publicar", "compartir",
    "cerrar sesion", "desconectar", "salir", "cerrar", "instalar",
    "desinstalar", "actualizar", "formatear", "aceptar", "acepto",
    "aceptar terminos", "confirmar", "restablecer", "reiniciar", "apagar",
    "imprimir", "sobrescribir", "firmar", "suscribir", "suscribirse",
    "transferir", "papelera", "nuevo", "nueva", "ejecutar", "iniciar",
    "detener", "parar", "llamar", "grabar", "sincronizar", "subir",
    "descargar", "exportar", "importar", "pegar", "cortar", "aplicar",
    "deshacer", "rehacer", "renombrar", "mover", "enviar a", "finalizar",
    "terminar", "bloquear", "desbloquear", "registrar", "registrarse",
    "iniciar sesion", "permitir", "autorizar", "reparar", "restaurar",
)
FORBIDDEN_TERMS_EN: Tuple[str, ...] = (
    "save", "save as", "send", "forward", "reply", "delete", "remove",
    "erase", "clear", "empty", "discard", "buy", "purchase", "checkout",
    "order", "pay", "payment", "publish", "post", "share", "sign out",
    "log out", "logout", "sign off", "disconnect", "exit", "quit", "close",
    "install", "uninstall", "update", "upgrade", "format", "accept",
    "agree", "i agree", "accept terms", "confirm", "submit", "reset",
    "restart", "reboot", "shut down", "shutdown", "print", "overwrite",
    "sign", "subscribe", "transfer", "trash", "bin", "new", "run",
    "execute", "start", "stop", "call", "record", "sync", "upload",
    "download", "export", "import", "paste", "cut", "apply", "undo",
    "redo", "rename", "move", "finish", "terminate", "kill", "lock",
    "unlock", "register", "sign in", "log in", "login", "allow",
    "authorize", "repair", "restore", "end task",
)

# Pistas de icono / identificador que indican efecto (cierre, papelera...).
FORBIDDEN_ICON_HINTS: Tuple[str, ...] = (
    "close", "trash", "delete", "remove", "logout", "signout", "power",
    "exit", "quit", "minimize", "maximize", "shutdown",
)

# Etiquetas de un solo simbolo que representan cerrar o borrar.
FORBIDDEN_SYMBOL_LABELS = frozenset({"x", "\u00d7", "\u2715", "\u2716", "\u2717", "\u2718", "-", "_"})

ELLIPSIS_SUFFIXES = ("...", "\u2026")

# Dialogos que no se abren nunca: los de ficheros/impresion exponen nombres de
# ficheros del usuario o tienen efectos externos.
DIALOG_FORBIDDEN_TERMS: Tuple[str, ...] = (
    "abrir", "open", "examinar", "browse", "imprimir", "print", "importar",
    "import", "exportar", "export", "guardar", "save", "buscar archivo",
    "find file", "cuenta", "account", "contrasena", "password",
)


def _normalize_text(value: Any) -> str:
    """Minusculas, sin acentos ni puntuacion, espacios simples."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_term(normalized_text: str, terms: Sequence[str]) -> Optional[str]:
    padded = " %s " % normalized_text
    for term in terms:
        term_n = _normalize_text(term)
        if term_n and (" %s " % term_n) in padded:
            return term
    return None


def element_reference(node: AccessibilityNode, tree: Optional[AccessibilityTree] = None) -> Dict[str, Any]:
    """Referencia logica de un elemento (sin coordenadas) para reencontrarlo."""
    parent_name = ""
    if tree is not None and node.parent_id:
        parent = tree.get(node.parent_id)
        if parent is not None:
            parent_name = parent.name
    return {
        "identifier": node.identifier,
        "name": node.name,
        "control_type": node.control_type,
        "native_role": node.native_role,
        "parent_name": parent_name,
        "depth": node.depth,
    }


class ExplorationSafetyPolicy:
    """Decide si una accion de exploracion sobre un nodo es segura.

    Argumentos:
        allow_dialogs: permite ``open_dialog`` (elementos de menu cuyo texto
            acaba en puntos suspensivos). Desactivado por defecto.
        extra_forbidden_terms: terminos adicionales prohibidos.
    """

    def __init__(
        self,
        allow_dialogs: bool = False,
        extra_forbidden_terms: Optional[Sequence[str]] = None,
    ) -> None:
        self.allow_dialogs = bool(allow_dialogs)
        self.forbidden_terms: Tuple[str, ...] = (
            FORBIDDEN_TERMS_ES + FORBIDDEN_TERMS_EN + tuple(extra_forbidden_terms or ())
        )

    def allowed_actions(self) -> FrozenSet[str]:
        actions = {ACTION_EXPAND, ACTION_SELECT_TAB, ACTION_OPEN_MENU}
        if self.allow_dialogs:
            actions.add(ACTION_OPEN_DIALOG)
        return frozenset(actions)

    def label_of(self, node: AccessibilityNode) -> str:
        return " ".join(p for p in (node.name, node.identifier) if p).strip()

    def is_forbidden_label(self, node: AccessibilityNode) -> Tuple[bool, str]:
        """Comprueba solo la semantica de la etiqueta (sin la accion)."""
        raw_label = self.label_of(node)
        if not raw_label:
            return True, "control sin etiqueta: semantica desconocida"
        if raw_label.strip().casefold() in FORBIDDEN_SYMBOL_LABELS:
            return True, "etiqueta de simbolo de cierre/borrado"
        normalized = _normalize_text(raw_label)
        if not normalized:
            return True, "etiqueta sin texto reconocible"
        term = _contains_term(normalized, self.forbidden_terms)
        if term:
            return True, "accion prohibida por semantica: %s" % term
        identifier_n = _normalize_text(node.identifier).replace(" ", "")
        for hint in FORBIDDEN_ICON_HINTS:
            if hint in identifier_n:
                return True, "identificador con pista de icono prohibido: %s" % hint
        return False, ""

    def is_allowed(self, node: AccessibilityNode, action: str) -> Tuple[bool, str]:
        """Devuelve (permitido, motivo). Ante cualquier duda devuelve False."""
        if action in NEVER_ACTIONS:
            return False, "accion de escritura o con efecto: %s" % action
        if action not in self.allowed_actions():
            return False, "accion no admitida en exploracion: %s" % action
        if not node.enabled:
            return False, "control deshabilitado"
        if not node.visible or node.offscreen:
            return False, "control no visible o fuera de pantalla"
        forbidden, reason = self.is_forbidden_label(node)
        if forbidden:
            return False, reason
        native_actions = set(node.actions)
        if action == ACTION_EXPAND:
            if "expand" not in native_actions:
                return False, "el control no expone expandir"
            return True, "expandir"
        if action == ACTION_SELECT_TAB:
            if node.native_role not in TAB_ROLES or "select" not in native_actions:
                return False, "el control no es una pestana seleccionable"
            return True, "seleccionar pestana"
        if action == ACTION_OPEN_MENU:
            if node.native_role not in MENU_OPENER_ROLES:
                return False, "el control no abre un menu"
            if node.native_role in MENU_ITEM_ROLES and "expand" not in native_actions and "show_menu" not in native_actions:
                # Un elemento de menu hoja ejecuta un comando: nunca se pulsa.
                return False, "elemento de menu hoja (ejecuta un comando)"
            if not native_actions & {"expand", "show_menu", "invoke"}:
                return False, "el control no expone una accion para abrir el menu"
            return True, "abrir menu"
        if action == ACTION_OPEN_DIALOG:
            if node.native_role not in MENU_ITEM_ROLES or "invoke" not in native_actions:
                return False, "solo elementos de menu pueden abrir dialogos"
            if not str(node.name or "").rstrip().endswith(ELLIPSIS_SUFFIXES):
                return False, "el elemento de menu no anuncia un dialogo (sin puntos suspensivos)"
            term = _contains_term(_normalize_text(self.label_of(node)), DIALOG_FORBIDDEN_TERMS)
            if term:
                return False, "dialogo excluido (ficheros, impresion o credenciales): %s" % term
            return True, "abrir dialogo"
        return False, "accion desconocida"

    def candidate_action(self, node: AccessibilityNode) -> Optional[str]:
        """Accion de exploracion que tendria sentido para el nodo (sin validar)."""
        native_actions = set(node.actions)
        if node.native_role in TAB_ROLES and "select" in native_actions:
            return ACTION_SELECT_TAB
        if "expand" in native_actions:
            return ACTION_EXPAND
        if node.native_role in MENU_OPENER_ROLES and native_actions & {"show_menu", "invoke"}:
            if node.native_role in MENU_ITEM_ROLES:
                if self.allow_dialogs and str(node.name or "").rstrip().endswith(ELLIPSIS_SUFFIXES):
                    return ACTION_OPEN_DIALOG
                if "show_menu" not in native_actions:
                    return None
            return ACTION_OPEN_MENU
        return None


# ============================================================================
# MAPA DE ESTADOS
# ============================================================================


@dataclass
class UIStateNode:
    """Estado UI: huella de ventanas del proceso y firma logica de los arboles."""

    state_id: str
    window_fingerprint: str
    tree_hash: str
    visible_elements: List[str] = field(default_factory=list)
    depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "window_fingerprint": self.window_fingerprint,
            "tree_hash": self.tree_hash,
            "visible_elements": list(self.visible_elements),
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UIStateNode":
        return cls(
            state_id=str(data.get("state_id", "")),
            window_fingerprint=str(data.get("window_fingerprint", "")),
            tree_hash=str(data.get("tree_hash", "")),
            visible_elements=[str(v) for v in data.get("visible_elements", []) or []],
            depth=int(data.get("depth", 0) or 0),
        )


@dataclass
class UITransition:
    """Transicion accion -> estado resultante y su forma de volver."""

    from_state: str
    action: str
    element_ref: Dict[str, Any]
    to_state: str
    return_action: str
    verified_return: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state,
            "action": self.action,
            "element_ref": dict(self.element_ref),
            "to_state": self.to_state,
            "return_action": self.return_action,
            "verified_return": self.verified_return,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UITransition":
        return cls(
            from_state=str(data.get("from_state", "")),
            action=str(data.get("action", "")),
            element_ref=dict(data.get("element_ref") or {}),
            to_state=str(data.get("to_state", "")),
            return_action=str(data.get("return_action", "")),
            verified_return=bool(data.get("verified_return", False)),
        )


# Claves que nunca deben aparecer en la representacion logica (catalogo).
_PHYSICAL_KEYS = frozenset({
    "bbox", "box", "center", "coordinates", "x", "y", "left", "top", "right",
    "bottom", "width", "height", "rect", "bounds", "point", "monitor",
    "display_id", "dpi", "scale_factor", "pid", "hwnd", "window_id",
})


def _strip_physical(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_physical(v) for k, v in value.items() if str(k).casefold() not in _PHYSICAL_KEYS}
    if isinstance(value, list):
        return [_strip_physical(v) for v in value]
    return value


class UIStateMap:
    """Mapa de estados UI de una aplicacion (logico, sin coordenadas)."""

    def __init__(self, app_id: str = "") -> None:
        self.app_id = app_id
        self.states: Dict[str, UIStateNode] = {}
        self.transitions: List[UITransition] = []
        self.root_state_id: Optional[str] = None

    def add_state(self, state: UIStateNode) -> bool:
        """Anade el estado; devuelve False si ya existia (estado repetido)."""
        if state.state_id in self.states:
            return False
        self.states[state.state_id] = state
        if self.root_state_id is None:
            self.root_state_id = state.state_id
        return True

    def has_state(self, state_id: str) -> bool:
        return state_id in self.states

    def get_state(self, state_id: str) -> Optional[UIStateNode]:
        return self.states.get(state_id)

    def add_transition(self, transition: UITransition) -> None:
        for existing in self.transitions:
            if (
                existing.from_state == transition.from_state
                and existing.action == transition.action
                and existing.element_ref == transition.element_ref
            ):
                existing.to_state = transition.to_state
                existing.return_action = transition.return_action
                existing.verified_return = transition.verified_return
                return
        self.transitions.append(transition)

    def transitions_from(self, state_id: str) -> List[UITransition]:
        return [t for t in self.transitions if t.from_state == state_id]

    def path_to(self, state_id: str) -> Optional[List[UITransition]]:
        """Ruta de transiciones verificadas desde la raiz hasta el estado."""
        if self.root_state_id is None:
            return None
        if state_id == self.root_state_id:
            return []
        queue: Deque[Tuple[str, List[UITransition]]] = deque([(self.root_state_id, [])])
        seen = {self.root_state_id}
        while queue:
            current, path = queue.popleft()
            for transition in self.transitions_from(current):
                if not transition.verified_return or transition.to_state in seen:
                    continue
                new_path = path + [transition]
                if transition.to_state == state_id:
                    return new_path
                seen.add(transition.to_state)
                queue.append((transition.to_state, new_path))
        return None

    def to_logical_dict(self) -> Dict[str, Any]:
        """Representacion logica para el catalogo: sin coordenadas ni ids fisicos."""
        return _strip_physical({
            "app_id": self.app_id,
            "root_state_id": self.root_state_id,
            "states": [s.to_dict() for s in self.states.values()],
            "transitions": [t.to_dict() for t in self.transitions],
        })

    @classmethod
    def from_logical_dict(cls, data: Dict[str, Any]) -> "UIStateMap":
        state_map = cls(str(data.get("app_id", "") or ""))
        for raw in data.get("states", []) or []:
            if isinstance(raw, dict):
                state_map.states[str(raw.get("state_id"))] = UIStateNode.from_dict(raw)
        state_map.root_state_id = data.get("root_state_id") or None
        for raw in data.get("transitions", []) or []:
            if isinstance(raw, dict):
                state_map.transitions.append(UITransition.from_dict(raw))
        return state_map


def persist_state_map_logically(app_key: str, state_map: UIStateMap, memory_manager: Any = None) -> Tuple[bool, str]:
    """Guarda el mapa logico en la entidad de catalogo existente ``app_<clave>``.

    Solo actualiza una entidad que ya existe (no inventa entidades) y solo con
    la representacion logica (``to_logical_dict``), sin coordenadas, monitores,
    PID/ventanas ni rutas. Devuelve (guardado, motivo).
    """
    key = _normalize_text(app_key).replace(" ", "_")
    if not key:
        return False, "clave de aplicacion vacia"
    try:
        if memory_manager is None:
            from src.memory.storage import get_memory_manager

            memory_manager = get_memory_manager()
        entity_id = key if key.startswith("app_") else "app_%s" % key
        entity = memory_manager.get_entity(entity_id)
        if entity is None:
            return False, "la entidad %s no existe en el catalogo" % entity_id
        properties = dict(getattr(entity, "properties", {}) or {})
        properties["ui_state_map"] = state_map.to_logical_dict()
        entity.properties = properties
        try:
            from datetime import datetime, timezone

            entity.updated_at = datetime.now(timezone.utc).isoformat()
        except Exception as exc:  # pragma: no cover - fecha opcional
            logger.debug("persist_state_map_logically: fecha no actualizada: %s", exc)
        saved = bool(memory_manager.save_entity(entity))
        return saved, "guardado" if saved else "save_entity devolvio False"
    except Exception as exc:
        logger.warning("No se pudo guardar el mapa de estados de %s: %s", app_key, exc)
        return False, str(exc)


# ============================================================================
# PRESUPUESTO, PUNTO DE CONTROL Y RESULTADO
# ============================================================================


@dataclass
class ExplorationBudget:
    """Limites de la exploracion (configurables)."""

    max_depth: int = 3
    max_states: int = 60
    max_seconds: float = 120.0
    max_actions: int = 300
    settle_timeout: float = 2.0
    settle_poll: float = 0.1
    return_similarity: float = 0.97

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_depth": self.max_depth,
            "max_states": self.max_states,
            "max_seconds": self.max_seconds,
            "max_actions": self.max_actions,
            "settle_timeout": self.settle_timeout,
            "settle_poll": self.settle_poll,
            "return_similarity": self.return_similarity,
        }


@dataclass
class ExplorationCheckpoint:
    """Estado serializable para reanudar una exploracion interrumpida."""

    app_id: str
    mode: str
    root_state_id: Optional[str]
    frontier: List[List[Dict[str, Any]]] = field(default_factory=list)
    state_map: Dict[str, Any] = field(default_factory=dict)
    actions_performed: int = 0
    elapsed_seconds: float = 0.0
    skipped_forbidden: List[Dict[str, Any]] = field(default_factory=list)
    target_ref: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "mode": self.mode,
            "root_state_id": self.root_state_id,
            "frontier": [list(path) for path in self.frontier],
            "state_map": dict(self.state_map),
            "actions_performed": self.actions_performed,
            "elapsed_seconds": self.elapsed_seconds,
            "skipped_forbidden": list(self.skipped_forbidden),
            "target_ref": dict(self.target_ref) if self.target_ref else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExplorationCheckpoint":
        return cls(
            app_id=str(data.get("app_id", "") or ""),
            mode=str(data.get("mode", "full") or "full"),
            root_state_id=data.get("root_state_id") or None,
            frontier=[list(p) for p in data.get("frontier", []) or []],
            state_map=dict(data.get("state_map") or {}),
            actions_performed=int(data.get("actions_performed", 0) or 0),
            elapsed_seconds=float(data.get("elapsed_seconds", 0.0) or 0.0),
            skipped_forbidden=list(data.get("skipped_forbidden", []) or []),
            target_ref=data.get("target_ref") or None,
        )

    @classmethod
    def from_json(cls, text: str) -> "ExplorationCheckpoint":
        return cls.from_dict(json.loads(text))


@dataclass
class ExplorationResult:
    """Resultado de una exploracion."""

    state_map: UIStateMap
    visited: List[str] = field(default_factory=list)
    skipped_forbidden: List[Dict[str, Any]] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""
    checkpoint: Optional[ExplorationCheckpoint] = None
    actions_performed: int = 0
    elapsed_seconds: float = 0.0
    budget_exhausted: str = ""
    target_found: bool = False
    target_path: List[Dict[str, Any]] = field(default_factory=list)
    closed_windows: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_map": self.state_map.to_logical_dict(),
            "visited": list(self.visited),
            "states": len(self.state_map.states),
            "transitions": len(self.state_map.transitions),
            "skipped_forbidden": list(self.skipped_forbidden),
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "actions_performed": self.actions_performed,
            "elapsed_seconds": self.elapsed_seconds,
            "budget_exhausted": self.budget_exhausted,
            "target_found": self.target_found,
            "target_path": list(self.target_path),
            "closed_windows_count": len(self.closed_windows),
            "errors": list(self.errors),
        }


# ============================================================================
# OBSERVACION DEL ESTADO
# ============================================================================


@dataclass
class _ObservedState:
    """Observacion de las ventanas del proceso y sus arboles."""

    window_ids: FrozenSet[int]
    trees: Dict[int, AccessibilityTree]
    signature: FrozenSet[Tuple[Any, ...]]
    state_id: str
    window_fingerprint: str
    tree_hash: str
    foreground_pid: Optional[int] = None
    foreground_window: Optional[int] = None

    def nodes(self) -> List[AccessibilityNode]:
        result: List[AccessibilityNode] = []
        for wid in sorted(self.trees):
            result.extend(self.trees[wid].nodes)
        return result

    def tree_for(self, node: AccessibilityNode) -> Optional[AccessibilityTree]:
        if node.window_id is not None and node.window_id in self.trees:
            return self.trees[node.window_id]
        for tree in self.trees.values():
            if tree.get(node.node_id) is not None:
                return tree
        return None


def _node_signature(window_id: int, node: AccessibilityNode) -> Tuple[Any, ...]:
    return (
        int(window_id), node.native_role, node.name, node.identifier,
        int(node.depth), bool(node.enabled), bool(node.visible), bool(node.offscreen),
    )


def _similarity(a: FrozenSet[Any], b: FrozenSet[Any]) -> float:
    if not a and not b:
        return 1.0
    union = len(a | b)
    return float(len(a & b)) / float(union) if union else 1.0


class _ExplorationAbort(Exception):
    """Parada segura de la exploracion con motivo."""


# ============================================================================
# EXPLORADOR
# ============================================================================


class DeepUIExplorer:
    """Explorador en anchura, acotado y reanudable, sobre el contrato de escritorio.

    Argumentos:
        adapter: adaptador de escritorio (por defecto ``get_desktop_platform()``).
        policy: politica de seguridad (por defecto ``ExplorationSafetyPolicy()``).
        budget: presupuesto (por defecto ``ExplorationBudget()``).
        store: almacen de perfiles de calibracion (opcional; la geometria fisica
            de los controles se persiste en los perfiles, no aqui).
        app_id: identificador estable de la aplicacion para el mapa.
    """

    def __init__(
        self,
        adapter: Any = None,
        policy: Optional[ExplorationSafetyPolicy] = None,
        budget: Optional[ExplorationBudget] = None,
        store: Any = None,
        app_id: str = "",
    ) -> None:
        if adapter is None:
            from src.desktop.platform_contract import get_desktop_platform

            adapter = get_desktop_platform()
        self.adapter = adapter
        self.policy = policy or ExplorationSafetyPolicy()
        self.budget = budget or ExplorationBudget()
        self.store = store
        self.app_id = app_id
        self._stop_event = threading.Event()
        self._wait_event = threading.Event()
        self._baseline_windows: FrozenSet[int] = frozenset()
        self._main_window_id: int = 0
        self._pid: Optional[int] = None
        self._started_at = 0.0
        self._elapsed_before = 0.0
        self._actions = 0
        self._performed_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Control externo
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        """Solicita una parada segura (se vuelve a la raiz y se emite checkpoint)."""
        self._stop_event.set()

    @property
    def performed_actions(self) -> List[Dict[str, Any]]:
        """Acciones realmente ejecutadas (para auditoria y pruebas)."""
        return list(self._performed_log)

    # ------------------------------------------------------------------
    # Observacion
    # ------------------------------------------------------------------

    def _list_process_windows(self) -> List[int]:
        ids: List[int] = []
        try:
            result = self.adapter.list_windows(pid=self._pid, visible_only=True)
            if result.ok and result.value:
                ids = [int(w.window_id) for w in result.value]
        except Exception as exc:
            logger.debug("[EXPLORACION] list_windows fallo: %s", exc)
        if self._main_window_id and self._main_window_id not in ids:
            # La ventana principal puede no listarse si el adaptador filtra; se
            # comprueba explicitamente.
            try:
                main = self.adapter.get_window(self._main_window_id)
                if main.ok:
                    ids.append(self._main_window_id)
            except Exception as exc:
                logger.debug("[EXPLORACION] get_window fallo: %s", exc)
        return sorted(set(ids))

    def _observe_once(self) -> _ObservedState:
        window_ids = self._list_process_windows()
        trees: Dict[int, AccessibilityTree] = {}
        for wid in window_ids:
            try:
                result = self.adapter.get_accessibility_tree(wid, pid=self._pid)
            except Exception as exc:
                logger.debug("[EXPLORACION] arbol de %s no disponible: %s", wid, exc)
                continue
            if result.ok and result.value is not None:
                trees[wid] = result.value
        signature_items: Set[Tuple[Any, ...]] = set()
        # La ventana principal se identifica como 0 en la firma para que el
        # estado no dependa de su id (que cambia entre sesiones); las ventanas
        # adicionales se marcan como 1 (ventana abierta por la interaccion).
        for wid, tree in trees.items():
            slot = 0 if wid == self._main_window_id else 1
            for node in tree.nodes:
                signature_items.add(_node_signature(slot, node))
        signature = frozenset(signature_items)
        window_fp = hashlib.sha256(
            ("%d:%d" % (len(window_ids), int(self._main_window_id in window_ids))).encode("ascii")
        ).hexdigest()[:16]
        tree_hash = hashlib.sha256(
            "\n".join(repr(item) for item in sorted(signature, key=repr)).encode("utf-8", "replace")
        ).hexdigest()
        state_id = hashlib.sha256((window_fp + tree_hash).encode("ascii")).hexdigest()[:24]
        foreground_pid = None
        foreground_window = None
        try:
            fg = self.adapter.get_foreground_window()
            if fg.ok and fg.value is not None:
                foreground_pid = int(fg.value.pid)
                foreground_window = int(fg.value.window_id)
        except Exception as exc:
            logger.debug("[EXPLORACION] primer plano no disponible: %s", exc)
        return _ObservedState(
            window_ids=frozenset(window_ids),
            trees=trees,
            signature=signature,
            state_id=state_id,
            window_fingerprint=window_fp,
            tree_hash=tree_hash,
            foreground_pid=foreground_pid,
            foreground_window=foreground_window,
        )

    def _observe(self) -> _ObservedState:
        """Observa hasta que dos lecturas consecutivas coinciden (sin sleep fijo)."""
        deadline = time.monotonic() + max(0.0, float(self.budget.settle_timeout))
        previous = self._observe_once()
        while time.monotonic() < deadline:
            self._wait_event.wait(max(0.0, float(self.budget.settle_poll)))
            current = self._observe_once()
            if current.state_id == previous.state_id:
                return current
            previous = current
        return previous

    def _state_node(self, observed: _ObservedState, depth: int) -> UIStateNode:
        visible = []
        for node in observed.nodes():
            if node.visible and not node.offscreen and (node.name or node.identifier):
                label = node.identifier or node.name
                if label not in visible:
                    visible.append(label)
        return UIStateNode(
            state_id=observed.state_id,
            window_fingerprint=observed.window_fingerprint,
            tree_hash=observed.tree_hash,
            visible_elements=visible[:200],
            depth=depth,
        )

    # ------------------------------------------------------------------
    # Localizacion y acciones
    # ------------------------------------------------------------------

    @staticmethod
    def _matches(node: AccessibilityNode, ref: Dict[str, Any], tree: Optional[AccessibilityTree]) -> bool:
        if ref.get("identifier"):
            if node.identifier != ref.get("identifier"):
                return False
        elif ref.get("name"):
            if node.name != ref.get("name"):
                return False
        else:
            return False
        if ref.get("native_role") and node.native_role != ref.get("native_role"):
            return False
        if ref.get("parent_name") and tree is not None and node.parent_id:
            parent = tree.get(node.parent_id)
            if parent is not None and parent.name != ref.get("parent_name"):
                return False
        return True

    def _locate(self, observed: _ObservedState, ref: Dict[str, Any]) -> Optional[AccessibilityNode]:
        matches = []
        for wid, tree in observed.trees.items():
            for node in tree.nodes:
                if self._matches(node, ref, tree):
                    matches.append(node)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            same_depth = [n for n in matches if n.depth == int(ref.get("depth", n.depth))]
            if len(same_depth) == 1:
                return same_depth[0]
        return None

    def _check_budget(self) -> Optional[str]:
        if self._stop_event.is_set():
            return "detenida por solicitud"
        elapsed = self._elapsed_before + (time.monotonic() - self._started_at)
        if elapsed >= float(self.budget.max_seconds):
            return "presupuesto de tiempo agotado"
        if self._actions >= int(self.budget.max_actions):
            return "presupuesto de acciones agotado"
        return None

    def _native_action_for(self, node: AccessibilityNode, action: str) -> str:
        native = set(node.actions)
        if action == ACTION_EXPAND:
            return "expand"
        if action == ACTION_SELECT_TAB:
            return "select"
        if action == ACTION_OPEN_MENU:
            if "show_menu" in native:
                return "show_menu"
            if "expand" in native:
                return "expand"
            return "invoke"
        if action == ACTION_OPEN_DIALOG:
            return "invoke"
        raise _ExplorationAbort("accion sin traduccion nativa: %s" % action)

    def _perform(self, node: AccessibilityNode, action: str) -> None:
        allowed, reason = self.policy.is_allowed(node, action)
        if not allowed:
            # Defensa en profundidad: nunca se ejecuta algo que la politica rechaza.
            raise _ExplorationAbort("accion rechazada por la politica en ejecucion: %s" % reason)
        native_action = self._native_action_for(node, action)
        window_id = int(node.window_id or self._main_window_id)
        self._actions += 1
        self._performed_log.append({
            "action": action,
            "native_action": native_action,
            "element_ref": element_reference(node),
        })
        result = self.adapter.perform_accessibility_action(window_id, node.node_id, native_action)
        if not result.ok:
            raise _ExplorationAbort(
                "la accion %s sobre %r fallo: %s"
                % (action, node.name or node.identifier, result.error)
            )

    def _foreground_is_own(self, observed: Optional[_ObservedState] = None) -> bool:
        if observed is not None and observed.foreground_pid is not None:
            return self._pid is not None and observed.foreground_pid == self._pid
        try:
            fg = self.adapter.get_foreground_window()
            if fg.ok and fg.value is not None:
                return self._pid is not None and int(fg.value.pid) == int(self._pid)
        except Exception as exc:
            logger.debug("[EXPLORACION] comprobacion de primer plano fallo: %s", exc)
        return False

    def _press_escape(self) -> bool:
        # Antes de cualquier tecla: el primer plano debe ser una ventana del
        # proceso explorado. Si no, no se pulsa nada.
        if not self._foreground_is_own():
            return False
        self._actions += 1
        self._performed_log.append({"action": RETURN_ESCAPE, "native_action": "escape", "element_ref": {}})
        result = self.adapter.press_keys(["escape"])
        return bool(result.ok)

    def _returned(self, expected: _ObservedState, current: _ObservedState) -> bool:
        if current.window_ids != expected.window_ids:
            return False
        if current.state_id == expected.state_id:
            return True
        return _similarity(current.signature, expected.signature) >= float(self.budget.return_similarity)

    def _return_to(
        self,
        expected: _ObservedState,
        node_ref: Dict[str, Any],
        action: str,
        after: _ObservedState,
    ) -> Tuple[bool, str, _ObservedState]:
        """Vuelve al estado ``expected`` tras ``action``; devuelve (ok, metodo, observado)."""
        current = after
        if self._returned(expected, current):
            return True, "none", current

        attempts: List[str] = []
        if action == ACTION_EXPAND:
            attempts = [RETURN_COLLAPSE, RETURN_ESCAPE]
        elif action == ACTION_OPEN_MENU:
            attempts = [RETURN_ESCAPE, RETURN_COLLAPSE, RETURN_ESCAPE]
        elif action == ACTION_SELECT_TAB:
            attempts = [RETURN_SELECT_PREVIOUS_TAB]
        elif action == ACTION_OPEN_DIALOG:
            attempts = [RETURN_ESCAPE, RETURN_CLOSE_OPENED_WINDOW]

        for method in attempts:
            ok = False
            if method == RETURN_COLLAPSE:
                node = self._locate(current, node_ref)
                if node is not None and "collapse" in node.actions:
                    self._actions += 1
                    self._performed_log.append({
                        "action": RETURN_COLLAPSE, "native_action": "collapse",
                        "element_ref": dict(node_ref),
                    })
                    res = self.adapter.perform_accessibility_action(
                        int(node.window_id or self._main_window_id), node.node_id, "collapse"
                    )
                    ok = bool(res.ok)
            elif method == RETURN_ESCAPE:
                ok = self._press_escape()
            elif method == RETURN_SELECT_PREVIOUS_TAB:
                ok = self._restore_previous_tab(expected, current, node_ref)
            elif method == RETURN_CLOSE_OPENED_WINDOW:
                ok = bool(self._close_new_windows(current, expected.window_ids))
            if not ok:
                continue
            current = self._observe()
            if self._returned(expected, current):
                return True, method, current
        return False, "+".join(attempts) or "none", current

    def _restore_previous_tab(
        self, expected: _ObservedState, current: _ObservedState, node_ref: Dict[str, Any]
    ) -> bool:
        """Selecciona pestanas hermanas seguras hasta recuperar el estado esperado."""
        selected = self._locate(current, node_ref)
        if selected is None:
            return False
        tree = current.tree_for(selected)
        if tree is None:
            return False
        siblings = [
            n for n in tree.nodes
            if n.parent_id == selected.parent_id
            and n.node_id != selected.node_id
            and n.native_role in TAB_ROLES
        ]
        for sibling in siblings:
            allowed, _ = self.policy.is_allowed(sibling, ACTION_SELECT_TAB)
            if not allowed:
                continue
            ref = element_reference(sibling, tree)
            self._perform(sibling, ACTION_SELECT_TAB)
            observed = self._observe()
            if self._returned(expected, observed):
                return True
            relocated = self._locate(observed, ref)
            if relocated is None:
                return False
            current = observed
            tree = current.tree_for(relocated) or tree
        return False

    def _close_new_windows(self, observed: _ObservedState, baseline: FrozenSet[int]) -> List[int]:
        """Cierra (sin forzar) solo ventanas del proceso abiertas durante la exploracion."""
        closed: List[int] = []
        for wid in sorted(observed.window_ids - baseline):
            if wid == self._main_window_id or wid in self._baseline_windows:
                continue
            try:
                result = self.adapter.close_window(wid)
                if result.ok:
                    closed.append(wid)
            except Exception as exc:
                logger.warning("[EXPLORACION] no se pudo cerrar la ventana abierta %s: %s", wid, exc)
        return closed

    def _recover(self, result: ExplorationResult, reason: str) -> None:
        """Parada segura: cierra solo lo abierto por JARVIS y registra el estado."""
        result.aborted = True
        result.abort_reason = reason
        logger.warning("[EXPLORACION] parada segura: %s", reason)
        try:
            current = self._observe_once()
            if current.window_ids - self._baseline_windows:
                if self._press_escape():
                    current = self._observe()
            result.closed_windows.extend(self._close_new_windows(current, self._baseline_windows))
        except Exception as exc:
            result.errors.append("recuperacion: %s" % exc)
            logger.warning("[EXPLORACION] error durante la recuperacion: %s", exc)

    # ------------------------------------------------------------------
    # Recorrido
    # ------------------------------------------------------------------

    def _replay(
        self, root: _ObservedState, path: List[Dict[str, Any]]
    ) -> Tuple[_ObservedState, List[Tuple[_ObservedState, Dict[str, Any], str]]]:
        """Reproduce una ruta desde la raiz. Devuelve el estado final y la pila de vuelta."""
        stack: List[Tuple[_ObservedState, Dict[str, Any], str]] = []
        current = root
        for step in path:
            reason = self._check_budget()
            if reason:
                raise _ExplorationAbort(reason)
            node = self._locate(current, step["element_ref"])
            if node is None:
                raise _ExplorationAbort("no se reencontro el elemento %r al reproducir la ruta" % step["element_ref"].get("name"))
            stack.append((current, step["element_ref"], step["action"]))
            self._perform(node, step["action"])
            current = self._observe()
        return current, stack

    def _unwind(
        self,
        stack: List[Tuple[_ObservedState, Dict[str, Any], str]],
        current: _ObservedState,
        root: Optional[_ObservedState] = None,
    ) -> _ObservedState:
        """Deshace la ruta hasta la raiz verificando cada vuelta.

        Si una vuelta deja la interfaz directamente en el estado raiz (por
        ejemplo, cerrar un dialogo abierto desde un menu cierra tambien el
        menu), el objetivo ya esta cumplido y se termina.
        """
        while stack:
            if root is not None and self._returned(root, current):
                return current
            expected, ref, action = stack.pop()
            ok, method, current = self._return_to(expected, ref, action, current)
            if not ok and root is not None and self._returned(root, current):
                return current
            if not ok:
                raise _ExplorationAbort(
                    "no se pudo volver al estado anterior tras %s sobre %r (metodo %s)"
                    % (action, ref.get("name") or ref.get("identifier"), method)
                )
        return current

    def _new_nodes(self, state: _ObservedState, parent: Optional[_ObservedState]) -> List[AccessibilityNode]:
        if parent is None:
            return state.nodes()
        parent_sig = parent.signature
        result = []
        for wid, tree in state.trees.items():
            slot = 0 if wid == self._main_window_id else 1
            for node in tree.nodes:
                if _node_signature(slot, node) not in parent_sig:
                    result.append(node)
        return result

    def _has_safe_candidates(self, state: _ObservedState, parent: _ObservedState) -> bool:
        for node in self._new_nodes(state, parent):
            action = self.policy.candidate_action(node)
            if action is not None and self.policy.is_allowed(node, action)[0]:
                return True
        return False

    @staticmethod
    def _already_explored(state_map: UIStateMap, state_id: str, action: str, ref: Dict[str, Any]) -> bool:
        for transition in state_map.transitions_from(state_id):
            if transition.action == action and transition.element_ref == ref and transition.verified_return:
                return True
        return False

    def _target_visible(self, observed: _ObservedState, target_ref: Optional[Dict[str, Any]]) -> bool:
        if not target_ref:
            return False
        node = self._locate(observed, target_ref)
        return node is not None and node.visible and not node.offscreen

    def explore(
        self,
        window_id: int,
        pid: Optional[int],
        mode: str = "full",
        target_ref: Optional[Dict[str, Any]] = None,
        checkpoint: Optional[ExplorationCheckpoint] = None,
    ) -> ExplorationResult:
        """Explora la aplicacion de la ventana ``window_id``.

        Argumentos:
            window_id: ventana principal ya identificada y preparada.
            pid: proceso de esa ventana (solo se observan sus ventanas).
            mode: ``"full"`` (todo dentro del presupuesto) o ``"branch"``
                (hasta que ``target_ref`` sea visible).
            target_ref: referencia logica del elemento buscado en modo branch
                (``identifier`` o ``name``, opcional ``native_role``).
            checkpoint: punto de control de una exploracion anterior.
        """
        if mode not in ("full", "branch"):
            raise ValueError("mode debe ser 'full' o 'branch'")
        if mode == "branch" and not target_ref:
            raise ValueError("mode='branch' requiere target_ref")

        self._stop_event.clear()
        self._main_window_id = int(window_id)
        self._pid = int(pid) if pid else None
        self._started_at = time.monotonic()
        self._actions = 0
        self._elapsed_before = 0.0

        state_map = UIStateMap(self.app_id)
        result = ExplorationResult(state_map=state_map)
        frontier: Deque[List[Dict[str, Any]]] = deque()

        try:
            main = self.adapter.get_window(self._main_window_id)
        except Exception as exc:
            main = None
            result.errors.append(str(exc))
        if main is None or not main.ok:
            result.aborted = True
            result.abort_reason = "la ventana principal no existe o no es accesible"
            return result

        root = self._observe()
        self._baseline_windows = root.window_ids
        if not root.trees:
            result.aborted = True
            result.abort_reason = "sin arbol de accesibilidad: la exploracion requiere accesibilidad"
            return result

        if checkpoint is not None:
            if checkpoint.root_state_id and checkpoint.root_state_id != root.state_id:
                # El id de estado se deriva de la firma logica (no de ids de
                # ventana): si difiere, la interfaz no esta en el mismo estado.
                result.aborted = True
                result.abort_reason = "el estado raiz no coincide con el punto de control"
                return result
            state_map = UIStateMap.from_logical_dict(checkpoint.state_map)
            state_map.app_id = self.app_id or state_map.app_id
            result.state_map = state_map
            frontier.extend(list(p) for p in checkpoint.frontier)
            self._actions = int(checkpoint.actions_performed)
            self._elapsed_before = float(checkpoint.elapsed_seconds)
            result.skipped_forbidden = list(checkpoint.skipped_forbidden)
            target_ref = target_ref or checkpoint.target_ref
            if not state_map.has_state(root.state_id):
                state_map.add_state(self._state_node(root, 0))
            state_map.root_state_id = root.state_id
        else:
            state_map.add_state(self._state_node(root, 0))
            state_map.root_state_id = root.state_id
            frontier.append([])

        result.visited = list(state_map.states)
        skipped_keys: Set[str] = set(
            json.dumps(item.get("element_ref", {}), sort_keys=True) for item in result.skipped_forbidden
        )
        parent_of: Dict[str, Optional[_ObservedState]] = {}

        if mode == "branch" and self._target_visible(root, target_ref):
            result.target_found = True

        try:
            while frontier and not result.target_found:
                reason = self._check_budget()
                if reason:
                    result.budget_exhausted = reason
                    break
                if len(state_map.states) >= int(self.budget.max_states):
                    result.budget_exhausted = "presupuesto de estados agotado"
                    break
                path = frontier.popleft()
                depth = len(path)
                if depth >= int(self.budget.max_depth):
                    continue

                current, stack = self._replay(root, path)
                parent_state = stack[-1][0] if stack else None
                candidates = self._new_nodes(current, parent_state)

                interrupted = False
                for node in candidates:
                    reason = self._check_budget()
                    if reason:
                        result.budget_exhausted = reason
                        interrupted = True
                        break
                    if len(state_map.states) >= int(self.budget.max_states):
                        result.budget_exhausted = "presupuesto de estados agotado"
                        interrupted = True
                        break
                    action = self.policy.candidate_action(node)
                    if action is None:
                        continue
                    tree = current.tree_for(node)
                    ref = element_reference(node, tree)
                    if self._already_explored(state_map, current.state_id, action, ref):
                        continue
                    allowed, why = self.policy.is_allowed(node, action)
                    if not allowed:
                        key = json.dumps(ref, sort_keys=True)
                        if key not in skipped_keys:
                            skipped_keys.add(key)
                            result.skipped_forbidden.append({"element_ref": ref, "action": action, "reason": why})
                        continue

                    # Los ids de nodo pueden cambiar tras volver: se relocaliza
                    # por referencia logica en el estado actual.
                    live = self._locate(current, ref)
                    if live is None:
                        result.errors.append("no se reencontro %r en el estado actual" % (ref.get("name") or ref.get("identifier")))
                        continue
                    try:
                        self._perform(live, action)
                    except _ExplorationAbort as exc:
                        probe = self._observe()
                        if self._returned(current, probe):
                            # La accion fallo sin cambiar la interfaz: se registra y se sigue.
                            result.errors.append(str(exc))
                            current = probe
                            continue
                        raise
                    after = self._observe()
                    if self._main_window_id not in after.window_ids:
                        raise _ExplorationAbort("la ventana principal desaparecio tras %s" % action)
                    if after.foreground_pid is not None and self._pid is not None and after.foreground_pid != self._pid:
                        raise _ExplorationAbort("una ventana de otro proceso paso a primer plano tras %s" % action)

                    is_new = state_map.add_state(self._state_node(after, depth + 1))
                    ok, method, back = self._return_to(current, ref, action, after)
                    if not ok and action == ACTION_OPEN_DIALOG and self._returned(root, back) and path:
                        # Invocar un elemento de menu cierra el menu: al cerrar el
                        # dialogo se vuelve a la raiz y se reproduce la ruta.
                        back, _ = self._replay(root, path)
                        ok = self._returned(current, back)
                        method = "%s+replay" % method
                    state_map.add_transition(UITransition(
                        from_state=current.state_id,
                        action=action,
                        element_ref=ref,
                        to_state=after.state_id,
                        return_action=method,
                        verified_return=ok,
                    ))
                    if not ok:
                        raise _ExplorationAbort(
                            "no se pudo volver al estado anterior tras %s sobre %r"
                            % (action, ref.get("name") or ref.get("identifier"))
                        )
                    current = back
                    if after.state_id not in result.visited:
                        result.visited.append(after.state_id)
                    if mode == "branch" and self._target_visible(after, target_ref):
                        result.target_found = True
                        result.target_path = [dict(s) for s in path] + [{"action": action, "element_ref": ref}]
                        break
                    if (
                        is_new
                        and after.state_id != current.state_id
                        and self._has_safe_candidates(after, current)
                    ):
                        # Solo se encola si el nuevo estado ofrece algo seguro
                        # que explorar (evita reproducir rutas inutilmente).
                        frontier.append(path + [{"action": action, "element_ref": ref}])

                if interrupted:
                    # El estado se reprocesa al reanudar; las transiciones ya
                    # registradas se omiten.
                    frontier.appendleft(path)
                self._unwind(stack, current, root)
        except _ExplorationAbort as exc:
            self._recover(result, str(exc))
        except Exception as exc:  # error inesperado: parada segura igualmente
            logger.exception("[EXPLORACION] error inesperado")
            self._recover(result, "error inesperado: %s" % exc)

        result.actions_performed = self._actions
        result.elapsed_seconds = self._elapsed_before + (time.monotonic() - self._started_at)
        if frontier or result.budget_exhausted or result.aborted:
            result.checkpoint = ExplorationCheckpoint(
                app_id=self.app_id,
                mode=mode,
                root_state_id=state_map.root_state_id,
                frontier=[list(p) for p in frontier],
                state_map=state_map.to_logical_dict(),
                actions_performed=self._actions,
                elapsed_seconds=result.elapsed_seconds,
                skipped_forbidden=list(result.skipped_forbidden),
                target_ref=dict(target_ref) if target_ref else None,
            )
        logger.info(
            "[EXPLORACION] %s: estados=%d transiciones=%d acciones=%d prohibidos=%d abortada=%s",
            self.app_id or "app", len(state_map.states), len(state_map.transitions),
            self._actions, len(result.skipped_forbidden), result.aborted,
        )
        return result


__all__ = [
    "ACTION_EXPAND",
    "ACTION_SELECT_TAB",
    "ACTION_OPEN_MENU",
    "ACTION_OPEN_DIALOG",
    "EXPLORATION_ACTIONS",
    "FORBIDDEN_TERMS_ES",
    "FORBIDDEN_TERMS_EN",
    "ExplorationSafetyPolicy",
    "UIStateNode",
    "UITransition",
    "UIStateMap",
    "ExplorationBudget",
    "ExplorationCheckpoint",
    "ExplorationResult",
    "DeepUIExplorer",
    "element_reference",
    "persist_state_map_logically",
]
