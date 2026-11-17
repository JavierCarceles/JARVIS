"""
Modelo unico del arbol de accesibilidad para Windows (UI Automation) y macOS (AX).

Normaliza los nodos de ambos SO a ``AccessibilityNode`` con: tipo de control
canonico (vocabulario de ``UIElementData``), rol nativo original, nombre,
identificador, caja en el espacio de escritorio nativo, habilitado, visible,
fuera de pantalla y acciones disponibles normalizadas. El rol, los patrones y
las acciones nativas se conservan como dato; nunca se deducen capacidades del
nombre, del icono ni del tipo visual.

``AccessibilityNode.to_ui_element_data()`` produce el modelo canonico
``UIElementData`` con su ``classification`` calculada por ``classify_element``.

Este modulo no llama a ninguna API nativa: recibe objetos ya leidos por el
adaptador de plataforma (``UIAutomationTree`` en Windows, diccionarios de
atributos AX en macOS).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.core.log import get_logger
from src.core.ui_element_model import (
    ElementClassification,
    UIElementData,
    classify_element,
    normalize_element_type,
)
from src.desktop.platform_contract import DESKTOP_PIXELS, DESKTOP_POINTS, Rect

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tablas de normalizacion
# ---------------------------------------------------------------------------

# Patron UIA -> acciones normalizadas que habilita.
UIA_PATTERN_ACTIONS: Dict[str, List[str]] = {
    "Invoke": ["invoke"],
    "Toggle": ["toggle"],
    "ExpandCollapse": ["expand", "collapse"],
    "SelectionItem": ["select"],
    "Value": ["set_value"],
    "RangeValue": ["set_value"],
    "Scroll": ["scroll"],
    "ScrollItem": ["scroll"],
}

# Accion AX -> accion normalizada.
AX_ACTION_MAP: Dict[str, str] = {
    "AXPress": "invoke",
    "AXConfirm": "invoke",
    "AXPick": "select",
    "AXShowMenu": "show_menu",
    "AXIncrement": "set_value",
    "AXDecrement": "set_value",
    "AXRaise": "focus",
    "AXCancel": "collapse",
}

# Accion normalizada -> nombre de patron UIA equivalente para classify_element
# (que solo conoce el vocabulario de patrones UIA).
ACTION_TO_EQUIVALENT_PATTERN: Dict[str, str] = {
    "invoke": "Invoke",
    "toggle": "Toggle",
    "expand": "ExpandCollapse",
    "collapse": "ExpandCollapse",
    "select": "Selection",
    "set_value": "Value",
    "scroll": "Scroll",
    "show_menu": "ExpandCollapse",
}

# ControlType UIA (nombre que devuelve pywinauto/COM) -> tipo libre que
# ``normalize_element_type`` convierte al canonico.
UIA_CONTROL_TYPE_HINTS: Dict[str, str] = {
    "Button": "button",
    "SplitButton": "button",
    "Hyperlink": "link",
    "CheckBox": "checkbox",
    "RadioButton": "radio",
    "ComboBox": "select",
    "List": "select",
    "Edit": "input",
    "Document": "field",
    "Text": "text",
    "Menu": "menu",
    "MenuBar": "menu",
    "MenuItem": "menu",
    "ToolBar": "toolbar",
    "Tab": "toolbar",
    "TabItem": "button",
    "ListItem": "element",
    "TreeItem": "element",
    "Slider": "element",
    "Spinner": "element",
    "Pane": "element",
    "Window": "element",
    "Group": "element",
    "Image": "element",
}

# Rol AX -> tipo libre que ``normalize_element_type`` convierte al canonico.
AX_ROLE_HINTS: Dict[str, str] = {
    "AXButton": "button",
    "AXPopUpButton": "select",
    "AXMenuButton": "button",
    "AXLink": "link",
    "AXCheckBox": "checkbox",
    "AXRadioButton": "radio",
    "AXComboBox": "select",
    "AXTextField": "input",
    "AXSecureTextField": "input",
    "AXSearchField": "input",
    "AXTextArea": "field",
    "AXStaticText": "text",
    "AXMenu": "menu",
    "AXMenuBar": "menu",
    "AXMenuBarItem": "menu",
    "AXMenuItem": "menu",
    "AXToolbar": "toolbar",
    "AXTabGroup": "toolbar",
    "AXRadioGroup": "toolbar",
    "AXList": "select",
    "AXOutline": "element",
    "AXRow": "element",
    "AXCell": "element",
    "AXSlider": "element",
    "AXImage": "element",
    "AXGroup": "element",
    "AXScrollArea": "element",
    "AXWindow": "element",
    "AXSheet": "element",
    "AXDialog": "element",
}

# Roles nativos que representan elementos transitorios (menus desplegados,
# popups, tooltips). Se usan en interfaces dinamicas.
TRANSIENT_NATIVE_ROLES = frozenset({
    "Menu", "ToolTip", "AXMenu", "AXHelpTag", "AXPopover", "AXSheet",
})


def _canonical_type(native_role: str, hints: Dict[str, str]) -> str:
    hint = hints.get(native_role or "", native_role or "")
    return normalize_element_type(hint)


def _stable_node_id(parts: Sequence[Any]) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------


@dataclass
class AccessibilityNode:
    """Nodo de accesibilidad normalizado (comun a Windows y macOS)."""

    node_id: str
    control_type: str
    native_role: str
    name: str = ""
    identifier: str = ""
    value: str = ""
    bbox: Optional[Rect] = None
    enabled: bool = False
    visible: bool = False
    offscreen: bool = False
    focusable: bool = False
    actions: List[str] = field(default_factory=list)
    native_patterns: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    depth: int = 0
    pid: Optional[int] = None
    window_id: Optional[int] = None
    framework: str = ""
    source: str = ""
    coordinate_space: str = DESKTOP_PIXELS
    native_ref: Any = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_transient(self) -> bool:
        return self.native_role in TRANSIENT_NATIVE_ROLES

    @property
    def equivalent_patterns(self) -> List[str]:
        """Patrones UIA equivalentes (en macOS, derivados de acciones AX)."""
        if self.source == "uia":
            return list(self.native_patterns)
        result: List[str] = []
        for action in self.actions:
            pattern = ACTION_TO_EQUIVALENT_PATTERN.get(action)
            if pattern and pattern not in result:
                result.append(pattern)
        return result

    def classification(self) -> ElementClassification:
        return classify_element(
            self._base_element(),
            uia_patterns=self.equivalent_patterns,
            enabled=self.enabled,
            visible=self.visible,
            offscreen=self.offscreen,
        )

    def _base_element(self) -> UIElementData:
        bbox = list(self.bbox.to_int_tuple()) if self.bbox and self.bbox.is_valid() else None
        center = (
            [int(round(self.bbox.center[0])), int(round(self.bbox.center[1]))]
            if bbox
            else []
        )
        return UIElementData(
            name=self.name or self.identifier or self.native_role,
            type=self.control_type,
            description="",
            text=self.value,
            bbox=bbox,
            center=center,
            interactive=bool(self.actions),
            confidence=1.0 if self.source in ("uia", "ax") else 0.0,
            calibrated=False,
        )

    def to_ui_element_data(self) -> UIElementData:
        """Convierte al modelo canonico conservando el rol nativo como dato."""
        element = self._base_element()
        element.classification = self.classification()
        element.calibration_data = {
            "native_role": self.native_role,
            "identifier": self.identifier,
            "actions": list(self.actions),
            "native_patterns": list(self.native_patterns),
            "source": self.source,
            "coordinate_space": self.coordinate_space,
            "node_id": self.node_id,
        }
        return element

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "control_type": self.control_type,
            "native_role": self.native_role,
            "name": self.name,
            "identifier": self.identifier,
            "value": self.value,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "enabled": self.enabled,
            "visible": self.visible,
            "offscreen": self.offscreen,
            "focusable": self.focusable,
            "actions": list(self.actions),
            "native_patterns": list(self.native_patterns),
            "parent_id": self.parent_id,
            "depth": self.depth,
            "pid": self.pid,
            "window_id": self.window_id,
            "framework": self.framework,
            "source": self.source,
            "coordinate_space": self.coordinate_space,
            "classification": self.classification().value,
        }


@dataclass
class AccessibilityTree:
    """Arbol normalizado de UNA ventana identificada."""

    window_id: int
    pid: Optional[int]
    source: str
    nodes: List[AccessibilityNode] = field(default_factory=list)
    root_id: Optional[str] = None
    truncated: bool = False
    error: Optional[str] = None
    coordinate_space: str = DESKTOP_PIXELS
    elapsed_seconds: float = 0.0

    def get(self, node_id: str) -> Optional[AccessibilityNode]:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def children_of(self, node_id: str) -> List[AccessibilityNode]:
        return [n for n in self.nodes if n.parent_id == node_id]

    def ancestors_of(self, node_id: str) -> List[AccessibilityNode]:
        result: List[AccessibilityNode] = []
        current = self.get(node_id)
        guard = 0
        while current is not None and current.parent_id and guard < 1000:
            parent = self.get(current.parent_id)
            if parent is None:
                break
            result.append(parent)
            current = parent
            guard += 1
        return result

    def find(
        self,
        name: Optional[str] = None,
        identifier: Optional[str] = None,
        control_type: Optional[str] = None,
    ) -> List[AccessibilityNode]:
        """Busca nodos por identificador, nombre y/o tipo (todos los dados deben coincidir)."""
        result = []
        name_l = (name or "").strip().lower()
        for node in self.nodes:
            if identifier and node.identifier != identifier:
                continue
            if name_l and node.name.strip().lower() != name_l:
                continue
            if control_type and node.control_type != control_type:
                continue
            result.append(node)
        return result

    def actionable_nodes(self) -> List[AccessibilityNode]:
        return [
            n for n in self.nodes
            if n.classification() == ElementClassification.UIA_ACTIONABLE
        ]

    def structure_hash(self) -> str:
        """Huella del estado UI (roles, nombres, identificadores, estado y cajas).

        Sirve para detectar cambios entre deteccion y accion y para reconocer
        estados repetidos en la exploracion. No incluye valores de texto
        introducidos por el usuario.
        """
        parts = []
        for n in self.nodes:
            box = n.bbox.to_int_tuple() if n.bbox else None
            parts.append(
                "%s|%s|%s|%s|%d|%d|%d|%s" % (
                    n.native_role, n.name, n.identifier, n.depth,
                    int(n.enabled), int(n.visible), int(n.offscreen), box,
                )
            )
        return hashlib.sha256("\n".join(parts).encode("utf-8", "replace")).hexdigest()

    def to_ui_elements(self) -> List[UIElementData]:
        return [n.to_ui_element_data() for n in self.nodes]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "pid": self.pid,
            "source": self.source,
            "root_id": self.root_id,
            "truncated": self.truncated,
            "error": self.error,
            "coordinate_space": self.coordinate_space,
            "elapsed_seconds": self.elapsed_seconds,
            "node_count": len(self.nodes),
            "nodes": [n.to_dict() for n in self.nodes],
        }


# ---------------------------------------------------------------------------
# Normalizacion Windows (UI Automation)
# ---------------------------------------------------------------------------


def _uia_node_id(element: Any, window_id: int) -> str:
    runtime_id = tuple(getattr(element, "runtime_id", ()) or ())
    if runtime_id:
        return "uia:" + ".".join(str(int(v)) for v in runtime_id)
    return "uia:" + _stable_node_id((
        window_id,
        getattr(element, "handle", 0),
        getattr(element, "automation_id", ""),
        getattr(element, "control_type", ""),
        getattr(element, "name", ""),
        getattr(element, "depth", 0),
        tuple(getattr(element, "bounding_rectangle", ()) or ()),
    ))


def normalize_uia_element(
    element: Any,
    window_id: int,
    parent_id: Optional[str] = None,
) -> AccessibilityNode:
    """Convierte un ``UIAutomationElement`` en ``AccessibilityNode``."""
    native_role = str(getattr(element, "control_type", "") or "")
    patterns = [str(p) for p in (getattr(element, "patterns", None) or [])]
    actions: List[str] = []
    for pattern in patterns:
        for action in UIA_PATTERN_ACTIONS.get(pattern, []):
            if action not in actions:
                actions.append(action)
    rect = Rect.from_any(getattr(element, "bounding_rectangle", None))
    if rect is not None and not rect.is_valid():
        rect = None
    pid = getattr(element, "process_id", None)
    return AccessibilityNode(
        node_id=_uia_node_id(element, window_id),
        control_type=_canonical_type(native_role, UIA_CONTROL_TYPE_HINTS),
        native_role=native_role,
        name=str(getattr(element, "name", "") or ""),
        identifier=str(getattr(element, "automation_id", "") or ""),
        value="",
        bbox=rect,
        enabled=bool(getattr(element, "is_enabled", False)),
        visible=bool(getattr(element, "visible", False)),
        offscreen=bool(getattr(element, "is_offscreen", False)),
        focusable=False,
        actions=actions,
        native_patterns=patterns,
        parent_id=parent_id,
        depth=int(getattr(element, "depth", 0) or 0),
        pid=int(pid) if pid else None,
        window_id=int(window_id),
        framework=str(getattr(element, "framework", "") or ""),
        source="uia",
        coordinate_space=DESKTOP_PIXELS,
        native_ref=None,
        raw={
            "class_name": str(getattr(element, "class_name", "") or ""),
            "control_id": getattr(element, "control_id", 0),
            "handle": getattr(element, "handle", 0),
            "parent_handle": getattr(element, "parent_handle", 0),
            "framework_id": str(getattr(element, "framework_id", "") or ""),
        },
    )


def normalize_uia_tree(tree: Any) -> AccessibilityTree:
    """Convierte un ``UIAutomationTree`` (lista plana con profundidad) al modelo comun.

    Los padres se reconstruyen por profundidad en el orden de enumeracion
    (preorden), que es el que produce ``UIAutomationAdapter``.
    """
    window_id = int(getattr(tree, "window_handle", 0) or 0)
    elements = list(getattr(tree, "elements", None) or [])
    nodes: List[AccessibilityNode] = []
    stack: List[AccessibilityNode] = []
    seen: Dict[str, int] = {}
    for element in elements:
        depth = int(getattr(element, "depth", 0) or 0)
        while stack and stack[-1].depth >= depth:
            stack.pop()
        parent_id = stack[-1].node_id if stack else None
        node = normalize_uia_element(element, window_id, parent_id=parent_id)
        # Ids duplicados (proveedores incompletos): desambiguar sin perder el nodo.
        if node.node_id in seen:
            seen[node.node_id] += 1
            node.node_id = "%s#%d" % (node.node_id, seen[node.node_id])
        else:
            seen[node.node_id] = 0
        nodes.append(node)
        stack.append(node)
    pid = getattr(tree, "process_id", None)
    return AccessibilityTree(
        window_id=window_id,
        pid=int(pid) if pid else None,
        source="uia",
        nodes=nodes,
        root_id=nodes[0].node_id if nodes else None,
        truncated=bool(getattr(tree, "truncated", False)),
        error=getattr(tree, "error", None),
        coordinate_space=DESKTOP_PIXELS,
        elapsed_seconds=float(getattr(tree, "elapsed_seconds", 0.0) or 0.0),
    )


# ---------------------------------------------------------------------------
# Normalizacion macOS (AXUIElement)
# ---------------------------------------------------------------------------


def normalize_ax_attributes(
    attributes: Dict[str, Any],
    window_id: int,
    pid: Optional[int],
    parent_id: Optional[str],
    depth: int,
    path: str,
    native_ref: Any = None,
) -> AccessibilityNode:
    """Convierte los atributos AX ya leidos de un elemento a ``AccessibilityNode``.

    ``attributes`` es un diccionario plano con claves AX (``AXRole``,
    ``AXSubrole``, ``AXTitle``, ``AXDescription``, ``AXIdentifier``,
    ``AXValue``, ``AXPosition`` (x, y), ``AXSize`` (w, h), ``AXEnabled``,
    ``AXFocused``, ``AXHidden``) mas ``_actions`` (lista de nombres de acciones
    AX) y ``_onscreen`` (bool opcional calculado por el adaptador con la
    interseccion caja/pantallas). Posicion y tamano estan en puntos globales
    de Quartz (``DESKTOP_POINTS``).
    """
    role = str(attributes.get("AXRole") or "")
    subrole = str(attributes.get("AXSubrole") or "")
    title = attributes.get("AXTitle") or attributes.get("AXDescription") or ""
    identifier = str(attributes.get("AXIdentifier") or "")
    value = attributes.get("AXValue")
    position = attributes.get("AXPosition")
    size = attributes.get("AXSize")
    rect: Optional[Rect] = None
    try:
        if position is not None and size is not None:
            x, y = float(position[0]), float(position[1])
            w, h = float(size[0]), float(size[1])
            if w > 0 and h > 0:
                rect = Rect(x, y, x + w, y + h)
    except (TypeError, ValueError, IndexError):
        rect = None
    native_actions = [str(a) for a in (attributes.get("_actions") or [])]
    actions: List[str] = []
    for native in native_actions:
        mapped = AX_ACTION_MAP.get(native)
        if mapped and mapped not in actions:
            actions.append(mapped)
    settable = attributes.get("_value_settable")
    if settable and "set_value" not in actions:
        actions.append("set_value")
    hidden = bool(attributes.get("AXHidden", False))
    onscreen = attributes.get("_onscreen")
    offscreen = (onscreen is False) or rect is None
    enabled_raw = attributes.get("AXEnabled")
    enabled = bool(enabled_raw) if enabled_raw is not None else True
    node_id = "ax:" + _stable_node_id((window_id, path, role, identifier))
    return AccessibilityNode(
        node_id=node_id,
        control_type=_canonical_type(role, AX_ROLE_HINTS),
        native_role=role,
        name=str(title or ""),
        identifier=identifier,
        value=str(value) if isinstance(value, (str, int, float)) else "",
        bbox=rect,
        enabled=enabled,
        visible=not hidden and rect is not None,
        offscreen=offscreen,
        focusable=bool(attributes.get("_focusable", False)),
        actions=actions,
        native_patterns=native_actions,
        parent_id=parent_id,
        depth=int(depth),
        pid=int(pid) if pid else None,
        window_id=int(window_id),
        framework="cocoa",
        source="ax",
        coordinate_space=DESKTOP_POINTS,
        native_ref=native_ref,
        raw={"subrole": subrole, "path": path},
    )


def build_tree(
    window_id: int,
    pid: Optional[int],
    source: str,
    nodes: Iterable[AccessibilityNode],
    truncated: bool = False,
    error: Optional[str] = None,
    coordinate_space: str = DESKTOP_PIXELS,
    elapsed_seconds: float = 0.0,
) -> AccessibilityTree:
    node_list = list(nodes)
    return AccessibilityTree(
        window_id=int(window_id),
        pid=pid,
        source=source,
        nodes=node_list,
        root_id=node_list[0].node_id if node_list else None,
        truncated=truncated,
        error=error,
        coordinate_space=coordinate_space,
        elapsed_seconds=elapsed_seconds,
    )


__all__ = [
    "AccessibilityNode",
    "AccessibilityTree",
    "UIA_PATTERN_ACTIONS",
    "AX_ACTION_MAP",
    "ACTION_TO_EQUIVALENT_PATTERN",
    "TRANSIENT_NATIVE_ROLES",
    "normalize_uia_element",
    "normalize_uia_tree",
    "normalize_ax_attributes",
    "build_tree",
]
