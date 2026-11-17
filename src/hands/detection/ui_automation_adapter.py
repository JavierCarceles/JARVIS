"""
Adaptador de automatizacion de UI de Windows (UI Automation).

Capa reutilizable sobre pywinauto con backend="uia" y acceso al elemento
AutomationElement subyacente (COM/UIAutomationCore via comtypes) cuando el
backend de pywinauto no expone una propiedad o patron necesario.

Recibe el HWND/PID de una ventana YA IDENTIFICADA y consulta solo el arbol
UI Automation de esa ventana. Nunca enumera el escritorio ni ventanas ajenas.
Durante el descubrimiento solo se leen propiedades y patrones disponibles;
nunca se invocan patrones de accion (Invoke, Value, Toggle...) ni se modifica
el estado de la ventana.
"""

from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import sys as _sys

from src.desktop.native_imports import lazy_module as _lazy_module, lazy_windll as _lazy_windll

if _sys.platform == "win32":
    from pywinauto import application
    from pywinauto.uia_element_info import UIAElementInfo
else:
    application = _lazy_module("pywinauto.application", required_platform="win32")
    UIAElementInfo = Any  # solo se usa en anotaciones fuera de Windows

from src.core.log import get_logger
from src.desktop.screen_manager import ScreenManager

logger = get_logger(__name__)

# Patrones de control consultados (lectura solamente; nunca se invocan)
CONTROL_PATTERNS = (
    "Invoke",
    "Value",
    "Toggle",
    "Selection",
    "ExpandCollapse",
    "Scroll",
    "Text",
    "RangeValue",
    "Window",
    "Transform",
    "Grid",
    "GridItem",
    "SelectionItem",
    "ScrollItem",
    "Table",
    "TableItem",
    "LegacyIAccessible",
)

# Patrones que indican capacidad de interaccion/actionable
ACTIONABLE_PATTERNS = {
    "Invoke",
    "Value",
    "Toggle",
    "Selection",
    "ExpandCollapse",
    "Scroll",
    "Window",
    "Transform",
}

# Limites de seguridad para la enumeracion del arbol
MAX_ELEMENTS = 2000
MAX_DEPTH = 60

# ---------------------------------------------------------------------------
# Clasificacion de framework y registro de cobertura por framework (unidad 3.8.6.3.3.11)
# ---------------------------------------------------------------------------

class FrameworkCoverage:
    """Describe el nivel de soporte de UI Automation para un framework y el fallback disponible.

    No asume que pywinauto/UIA se comporte igual en todos los frameworks:
    cada entrada declara de forma independiente cuanta cobertura ofrece UIA,
    si es fiable y que fallback esta disponible (o None si no hay ninguno).
    """

    def __init__(
        self,
        framework: str,
        category: str,
        uia_coverage: str,
        uia_reliable: bool,
        fallback: Optional[str],
        fallback_available: bool,
        notes: str,
    ) -> None:
        self.framework = framework
        self.category = category
        self.uia_coverage = uia_coverage
        self.uia_reliable = uia_reliable
        self.fallback = fallback
        self.fallback_available = fallback_available
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework": self.framework,
            "category": self.category,
            "uia_coverage": self.uia_coverage,
            "uia_reliable": bool(self.uia_reliable),
            "fallback": self.fallback,
            "fallback_available": bool(self.fallback_available),
            "notes": self.notes,
        }


# CATEGORIAS DE FRAMEWORK
FRAMEWORK_CAT_DESKTOP_NATIVE = "desktop_native"
FRAMEWORK_CAT_BROWSER = "browser"
FRAMEWORK_CAT_CUSTOM_RENDER = "custom_render"
FRAMEWORK_CAT_PROTECTED = "protected"
FRAMEWORK_CAT_UNKNOWN = "unknown"

# NIVELES DE COBERTURA UIA
UIA_COVERAGE_FULL = "full"
UIA_COVERAGE_PARTIAL = "partial"
UIA_COVERAGE_NONE = "none"

# Fallbacks reconocidos (nombres logicos, no rutas ni coordenadas)
FALLBACK_NONE = None
FALLBACK_VISION_OCR = "vision_ocr"
FALLBACK_CDP = "chrome_devtools_protocol"
FALLBACK_QACCESSIBLE = "qaccessible"


# Registro de cobertura por framework. Cada clave es el nombre canonico de
# framework devuelto por classify_framework(). Ninguna entrada asume cobertura
# uniforme: cada framework declara su propio nivel y fallback.
FRAMEWORK_COVERAGE: Dict[str, FrameworkCoverage] = {
    "win32": FrameworkCoverage(
        framework="win32",
        category=FRAMEWORK_CAT_DESKTOP_NATIVE,
        uia_coverage=UIA_COVERAGE_FULL,
        uia_reliable=True,
        fallback=None,
        fallback_available=False,
        notes="Controles Win32 nativos. UI Automation expide arbol completo, patrones y geometria sin limitaciones conocidas.",
    ),
    "winforms": FrameworkCoverage(
        framework="winforms",
        category=FRAMEWORK_CAT_DESKTOP_NATIVE,
        uia_coverage=UIA_COVERAGE_FULL,
        uia_reliable=True,
        fallback=None,
        fallback_available=False,
        notes="Windows Forms. UI Automation suele exponer nombre, tipo, patrones y bounding box de forma fiable.",
    ),
    "wpf": FrameworkCoverage(
        framework="wpf",
        category=FRAMEWORK_CAT_DESKTOP_NATIVE,
        uia_coverage=UIA_COVERAGE_FULL,
        uia_reliable=True,
        fallback=None,
        fallback_available=False,
        notes="WPF. UI Automation expide arbol y patrones; algunos controles personalizados pueden no exponer AutomationId.",
    ),
    "uwp_appx": FrameworkCoverage(
        framework="uwp_appx",
        category=FRAMEWORK_CAT_DESKTOP_NATIVE,
        uia_coverage=UIA_COVERAGE_PARTIAL,
        uia_reliable=True,
        fallback=None,
        fallback_available=False,
        notes="UWP/AppX (DirectUI). UI Automation funciona pero algunos controles de la tienda tienen patrones limitados o jerarquia virtualizada.",
    ),
    "qt": FrameworkCoverage(
        framework="qt",
        category=FRAMEWORK_CAT_DESKTOP_NATIVE,
        uia_coverage=UIA_COVERAGE_PARTIAL,
        uia_reliable=False,
        fallback=FALLBACK_QACCESSIBLE,
        fallback_available=False,
        notes="Qt. UI Automation puede exponer arbol parcial; patrones y nombres dependen de la version de Qt y de QAccessibleBridge. No se asume cobertura completa.",
    ),
    "chromium_electron": FrameworkCoverage(
        framework="chromium_electron",
        category=FRAMEWORK_CAT_BROWSER,
        uia_coverage=UIA_COVERAGE_PARTIAL,
        uia_reliable=False,
        fallback=FALLBACK_CDP,
        fallback_available=False,
        notes="Chromium/Electron (Chrome, Edge, apps Electron). UI Automation ve el contenedor HWND pero el contenido renderizado (DOM/Canvas) no es accesible por UIA. Fallback: Chrome DevTools Protocol si el navegador lo expone con puerto de depuracion.",
    ),
    "browser_legacy": FrameworkCoverage(
        framework="browser_legacy",
        category=FRAMEWORK_CAT_BROWSER,
        uia_coverage=UIA_COVERAGE_PARTIAL,
        uia_reliable=False,
        fallback=None,
        fallback_available=False,
        notes="Navegadores legacy (IE, EdgeHTML). Cobertura parcial y no garantizada por UIA.",
    ),
    "browser_gecko": FrameworkCoverage(
        framework="browser_gecko",
        category=FRAMEWORK_CAT_BROWSER,
        uia_coverage=UIA_COVERAGE_PARTIAL,
        uia_reliable=False,
        fallback=None,
        fallback_available=False,
        notes="Motor Gecko (Firefox). UI Automation tiene soporte limitado; no se asume cobertura de contenido web.",
    ),
    "custom_drawn": FrameworkCoverage(
        framework="custom_drawn",
        category=FRAMEWORK_CAT_CUSTOM_RENDER,
        uia_coverage=UIA_COVERAGE_NONE,
        uia_reliable=False,
        fallback=FALLBACK_VISION_OCR,
        fallback_available=False,
        notes="Controles dibujados a medida (canvas, custom paint, DirectX/OpenGL, juegos). UI Automation no expone controles internos. Fallback: vision/OCR sobre captura de pantalla.",
    ),
    "directx_opengl": FrameworkCoverage(
        framework="directx_opengl",
        category=FRAMEWORK_CAT_CUSTOM_RENDER,
        uia_coverage=UIA_COVERAGE_NONE,
        uia_reliable=False,
        fallback=FALLBACK_VISION_OCR,
        fallback_available=False,
        notes="Superficies DirectX/OpenGL y juegos. UI Automation no accede al contenido renderizado. Fallback: vision/OCR.",
    ),
    "game": FrameworkCoverage(
        framework="game",
        category=FRAMEWORK_CAT_CUSTOM_RENDER,
        uia_coverage=UIA_COVERAGE_NONE,
        uia_reliable=False,
        fallback=FALLBACK_VISION_OCR,
        fallback_available=False,
        notes="Juegos y aplicaciones con renderizado propio. UI Automation no expide controles interactivos. Fallback: vision/OCR.",
    ),
    "overlay": FrameworkCoverage(
        framework="overlay",
        category=FRAMEWORK_CAT_CUSTOM_RENDER,
        uia_coverage=UIA_COVERAGE_PARTIAL,
        uia_reliable=False,
        fallback=None,
        fallback_available=False,
        notes="Overlays y ventanas flotantes. UI Automation puede ver la ventana pero no garantiza controles internos ni estabilidad de geometria.",
    ),
    "remote_content": FrameworkCoverage(
        framework="remote_content",
        category=FRAMEWORK_CAT_CUSTOM_RENDER,
        uia_coverage=UIA_COVERAGE_NONE,
        uia_reliable=False,
        fallback=None,
        fallback_available=False,
        notes="Contenido remoto (escritorio remoto, citrix, streaming). UI Automation no accede al contenido del lado remoto.",
    ),
    "protected_screen": FrameworkCoverage(
        framework="protected_screen",
        category=FRAMEWORK_CAT_PROTECTED,
        uia_coverage=UIA_COVERAGE_NONE,
        uia_reliable=False,
        fallback=None,
        fallback_available=False,
        notes="Pantallas protegidas (DRM, contenido protegido, ventanas de credenciales seguras). Captura e interaccion bloqueadas por el SO.",
    ),
    "unknown": FrameworkCoverage(
        framework="unknown",
        category=FRAMEWORK_CAT_UNKNOWN,
        uia_coverage=UIA_COVERAGE_NONE,
        uia_reliable=False,
        fallback=FALLBACK_VISION_OCR,
        fallback_available=False,
        notes="Framework no identificado. No se asume cobertura de UIA; se recomienda verificacion visual/OCR antes de cualquier interaccion.",
    ),
}


def classify_framework(
    framework_id: Optional[str],
    class_name: Optional[str] = None,
    control_type: Optional[str] = None,
) -> str:
    """Clasifica el framework de un control UI Automation.

    Argumentos:
        framework_id: valor bruto de CurrentFrameworkId del proveedor UIA.
        class_name: nombre de clase del control (pista secundaria).
        control_type: tipo de control UIA (pista secundaria).

    Retorna:
        Nombre canonico de framework: win32, winforms, wpf, uwp_appx, qt,
        chromium_electron, browser_legacy, browser_gecko, custom_drawn,
        directx_opengl, game, overlay, remote_content, protected_screen o unknown.

    Nota: framework_id vacio no se rellena por inferencia visual; se clasifica
    como custom_drawn si hay class_name (indica que UIA ve algo pero no sabe el
    framework) o unknown si no hay ninguna pista.
    """
    fid = (framework_id or "").strip()
    cls = (class_name or "").strip()
    ctype = (control_type or "").strip()

    if not fid:
        # framework_id vacio: UIA no expone el framework del proveedor.
        # Puede ser custom-drawn, DirectX, juego, overlay o desconocido.
        # No inferimos por class_name para no asumir: solo marcamos la pista.
        if cls:
            return "custom_drawn"
        return "unknown"

    fid_lower = fid.lower()

    if fid_lower == "win32":
        return "win32"
    if fid_lower == "winforms":
        return "winforms"
    if fid_lower == "wpf":
        return "wpf"
    if fid_lower in ("uwp", "directui", "windows.ui.xaml", "directuihost"):
        return "uwp_appx"
    if fid_lower in ("qt", "qwidget", "qquickwindow", "qwindow"):
        return "qt"
    if fid_lower in (
        "chrome", "chromium", "chrome_renderwidgethosthwnd",
        "chrome_legacy_window", "electron",
    ):
        return "chromium_electron"
    if fid_lower in ("ie", "internet_explorer", "edgehtml", "trident"):
        return "browser_legacy"
    if "firefox" in fid_lower or "mozilla" in fid_lower or "gecko" in fid_lower:
        return "browser_gecko"
    if "directx" in fid_lower or "opengl" in fid_lower or "d3d" in fid_lower:
        return "directx_opengl"
    if "game" in fid_lower or "unreal" in fid_lower or "unity" in fid_lower:
        return "game"
    if "overlay" in fid_lower:
        return "overlay"
    if "remote" in fid_lower or "citrix" in fid_lower or "rdp" in fid_lower:
        return "remote_content"
    if "protected" in fid_lower or "secure" in fid_lower:
        return "protected_screen"

    # framework_id no vacio pero no reconocido: se conserva tal cual en minusculas
    # como identificativo de framework desconocido.
    return "unknown"


def get_framework_coverage(framework: str) -> FrameworkCoverage:
    """Devuelve la cobertura registrada para un framework, o la entrada unknown si no esta registrada."""
    return FRAMEWORK_COVERAGE.get(framework, FRAMEWORK_COVERAGE["unknown"])


@dataclass
class UIAutomationElement:
    """Propiedades de un control del arbol UI Automation de una ventana."""

    automation_id: str = ""
    name: str = ""
    control_type: str = ""
    class_name: str = ""
    control_id: int = 0
    bounding_rectangle: Tuple[int, int, int, int] = (0, 0, 0, 0)
    process_id: int = 0
    runtime_id: Tuple[int, ...] = ()
    is_enabled: bool = False
    is_offscreen: bool = False
    visible: bool = False
    handle: int = 0
    framework_id: str = ""
    framework: str = ""
    parent_handle: int = 0
    child_count: int = 0
    patterns: List[str] = field(default_factory=list)
    depth: int = 0
    source: str = "uia"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "automation_id": self.automation_id,
            "name": self.name,
            "control_type": self.control_type,
            "class_name": self.class_name,
            "control_id": self.control_id,
            "bounding_rectangle": list(self.bounding_rectangle),
            "process_id": self.process_id,
            "runtime_id": list(self.runtime_id),
            "is_enabled": self.is_enabled,
            "is_offscreen": self.is_offscreen,
            "visible": self.visible,
            "handle": self.handle,
            "framework_id": self.framework_id,
            "framework": self.framework,
            "parent_handle": self.parent_handle,
            "child_count": self.child_count,
            "patterns": list(self.patterns),
            "depth": self.depth,
            "source": self.source,
        }


@dataclass
class UIAutomationTree:
    """Resultado de la enumeracion del arbol UI Automation de una ventana."""

    window_handle: int
    process_id: int
    window_title: str
    window_class: str
    root_element: UIAutomationElement
    elements: List[UIAutomationElement] = field(default_factory=list)
    element_count: int = 0
    truncated: bool = False
    error: Optional[str] = None
    source: str = "uia"
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_handle": self.window_handle,
            "process_id": self.process_id,
            "window_title": self.window_title,
            "window_class": self.window_class,
            "root_element": self.root_element.to_dict(),
            "elements": [e.to_dict() for e in self.elements],
            "element_count": self.element_count,
            "truncated": self.truncated,
            "error": self.error,
            "source": self.source,
            "elapsed_seconds": self.elapsed_seconds,
        }


class UIAutomationAdapter:
    """Adaptador reutilizable de Windows UI Automation.

    Se conecta a una ventana ya identificada mediante su HWND (y opcionalmente
    PID) usando pywinauto con backend="uia". Si el backend no expone una
    propiedad o patron necesario, se accede al elemento AutomationElement
    subyacente (COM/UIAutomationCore via comtypes).

    Nunca enumera el escritorio indiscriminadamente: solo consulta el arbol
    de la ventana cuyo HWND se proporciona.
    """

    def __init__(
        self,
        timeout: float = 10.0,
        max_depth: int = MAX_DEPTH,
        max_elements: int = MAX_ELEMENTS,
    ) -> None:
        self.timeout = timeout
        self.max_depth = max_depth
        self.max_elements = max_elements
        self._screen_manager = ScreenManager()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def enumerate_window(
        self, hwnd: int, pid: Optional[int] = None
    ) -> UIAutomationTree:
        """Enumera el arbol UI Automation de la ventana identificada por hwnd.

        Argumentos:
            hwnd: Identificador de ventana (HWND) de la ventana ya abierta.
            pid: Identificador de proceso opcional, usado para validacion.

        Retorna:
            UIAutomationTree con el arbol de controles de la ventana.
        """
        start = time.perf_counter()
        hwnd = int(hwnd)

        # Validar que la ventana existe y es accesible
        if not self._window_exists(hwnd):
            return UIAutomationTree(
                window_handle=hwnd,
                process_id=int(pid or 0),
                window_title="",
                window_class="",
                root_element=UIAutomationElement(),
                error="La ventana HWND=%s no existe o no es accesible" % hwnd,
                source="uia",
                elapsed_seconds=time.perf_counter() - start,
            )

        tree = self._enumerate_with_pywinauto(hwnd, pid, start)
        if tree.error is None and tree.element_count > 0:
            return tree

        # Si pywinauto fallo o no devolvio elementos, intentar acceso directo
        # al elemento AutomationElement (COM) como fallback.
        logger.debug(
            "[UI-AUTOMATION-ADAPTER] pywinauto no produjo arbol usable para "
            "HWND=%s; probando acceso directo al elemento AutomationElement",
            hwnd,
        )
        tree_direct = self._enumerate_with_automation_element(hwnd, pid, start)
        if tree_direct.error is None and tree_direct.element_count > 0:
            return tree_direct

        # Devolver el mejor resultado disponible
        if tree.error is None:
            return tree
        return tree_direct if tree_direct.error is None else tree

    def get_actionable_elements(
        self, tree: UIAutomationTree
    ) -> List[UIAutomationElement]:
        """Devuelve elementos que declaran al menos un patron de accion legible.

        Un elemento se considera candidato a interaccion si declara Invoke,
        Value, Toggle, Selection, ExpandCollapse, Scroll, Window o Transform,
        y esta habilitado, visible y no fuera de pantalla.

        Esta funcion solo clasifica; no verifica que la accion tenga efecto
        (eso corresponde a unidades posteriores de verificacion).
        """
        result: List[UIAutomationElement] = []
        for elem in tree.elements:
            if not (
                elem.visible
                and elem.is_enabled
                and elem.is_offscreen is False
            ):
                continue
            if any(p in ACTIONABLE_PATTERNS for p in elem.patterns):
                result.append(elem)
        return result

    # ------------------------------------------------------------------
    # Cobertura por framework (unidad 3.8.6.3.3.11)
    # ------------------------------------------------------------------

    def get_framework_coverage(self, framework: str) -> FrameworkCoverage:
        """Devuelve la informacion de cobertura registrada para un framework.

        Argumentos:
            framework: nombre canonico de framework (win32, wpf, qt,
                chromium_electron, custom_drawn, unknown, etc.).

        Retorna:
            FrameworkCoverage con cobertura UIA, fiabilidad y fallback.
        """
        return get_framework_coverage(framework)

    def get_framework_summary(self, tree: UIAutomationTree) -> Dict[str, Any]:
        """Resume la distribucion de frameworks y cobertura de un arbol UIA.

        Argumentos:
            tree: arbol UIAutomationTree ya enumerado.

        Retorna:
            Diccionario con:
              - total_elements: cantidad de elementos del arbol
              - by_framework: dict {nombre_framework: {count, coverage, uia_reliable, fallback, fallback_available}}
              - frameworks_detectados: lista de nombres canonicos presentes
              - frameworks_sin_cobertura: frameworks con cobertura none o unknown
              - elementos_con_framework_desconocido: count de elementos con framework unknown
        """
        by_framework: Dict[str, Dict[str, Any]] = {}
        frameworks_detectados: Set[str] = set()
        frameworks_sin_cobertura: List[str] = []
        elementos_desconocidos = 0

        for elem in tree.elements:
            fw = elem.framework or "unknown"
            frameworks_detectados.add(fw)
            coverage = get_framework_coverage(fw)

            if fw not in by_framework:
                by_framework[fw] = {
                    "count": 0,
                    "coverage": coverage.uia_coverage,
                    "uia_reliable": coverage.uia_reliable,
                    "fallback": coverage.fallback,
                    "fallback_available": coverage.fallback_available,
                    "notes": coverage.notes,
                }
            by_framework[fw]["count"] += 1

            if coverage.uia_coverage in (UIA_COVERAGE_NONE,) or fw == "unknown":
                if fw not in frameworks_sin_cobertura:
                    frameworks_sin_cobertura.append(fw)

            if fw == "unknown":
                elementos_desconocidos += 1

        return {
            "total_elements": len(tree.elements),
            "by_framework": by_framework,
            "frameworks_detectados": sorted(frameworks_detectados),
            "frameworks_sin_cobertura": frameworks_sin_cobertura,
            "elementos_con_framework_desconocido": elementos_desconocidos,
        }

    # ------------------------------------------------------------------
    # Enumeracion con pywinauto (uia)
    # ------------------------------------------------------------------

    def _window_exists(self, hwnd: int) -> bool:
        """Comprueba que el HWND corresponde a una ventana real de Windows."""
        try:
            return bool(ctypes.windll.user32.IsWindow(ctypes.c_void_p(hwnd)))
        except Exception:
            return False

    def _enumerate_with_pywinauto(
        self, hwnd: int, pid: Optional[int], start: float
    ) -> UIAutomationTree:
        """Enumera usando pywinauto con backend UI Automation."""
        try:
            app = application.Application(backend="uia").connect(
                handle=hwnd, timeout=self.timeout
            )
            window = app.window(handle=hwnd)
            element_info = window.element_info

            root = self._element_info_to_dataclass(
                element_info, depth=0, parent_handle=0, pid=pid
            )
            elements: List[UIAutomationElement] = [root]
            seen_handles: Set[int] = {root.handle} if root.handle else set()

            truncated = self._enumerate_children(
                element_info,
                root.handle,
                depth=1,
                elements=elements,
                seen_handles=seen_handles,
                pid=pid,
            )

            title = self._safe_text(element_info, "name") or ""
            class_name = self._safe_text(element_info, "class_name") or ""

            return UIAutomationTree(
                window_handle=hwnd,
                process_id=int(pid or root.process_id or 0),
                window_title=title,
                window_class=class_name,
                root_element=root,
                elements=elements,
                element_count=len(elements),
                truncated=truncated,
                source="uia",
                elapsed_seconds=time.perf_counter() - start,
            )
        except Exception as exc:
            logger.debug(
                "[UI-AUTOMATION-ADAPTER] pywinauto fallo para HWND=%s: %s",
                hwnd,
                exc,
            )
            return UIAutomationTree(
                window_handle=hwnd,
                process_id=int(pid or 0),
                window_title="",
                window_class="",
                root_element=UIAutomationElement(),
                error=str(exc),
                source="uia",
                elapsed_seconds=time.perf_counter() - start,
            )

    def _enumerate_children(
        self,
        parent_info: UIAElementInfo,
        parent_handle: int,
        depth: int,
        elements: List[UIAutomationElement],
        seen_handles: Set[int],
        pid: Optional[int],
    ) -> bool:
        """Enumera recursivamente los hijos directos de un elemento UIA.

        Retorna True si la enumeracion se detuvo por alcanzar el limite de
        profundidad o de elementos (arbol virtualizado o muy grande), False
        si se recorrieron todos los hijos disponibles sin cortes.
        """
        if depth > self.max_depth or len(elements) >= self.max_elements:
            return True
        hit_limit = False
        try:
            children = parent_info.children()
        except Exception as exc:
            logger.debug(
                "[UI-AUTOMATION-ADAPTER] No se pudieron leer hijos: %s", exc
            )
            return False
        for child in children:
            if len(elements) >= self.max_elements:
                hit_limit = True
                break
            try:
                child_elem = self._element_info_to_dataclass(
                    child,
                    depth=depth,
                    parent_handle=parent_handle,
                    pid=pid,
                )
                if child_elem.handle and child_elem.handle in seen_handles:
                    continue  # evitar duplicados y ciclos
                if child_elem.handle:
                    seen_handles.add(child_elem.handle)
                elements.append(child_elem)
                child_hit = self._enumerate_children(
                    child,
                    child_elem.handle,
                    depth + 1,
                    elements,
                    seen_handles,
                    pid,
                )
                if child_hit:
                    hit_limit = True
            except Exception as exc:
                logger.debug(
                    "[UI-AUTOMATION-ADAPTER] Error procesando hijo: %s", exc
                )
                continue
        return hit_limit

    def _element_info_to_dataclass(
        self,
        info: UIAElementInfo,
        depth: int = 0,
        parent_handle: int = 0,
        pid: Optional[int] = None,
    ) -> UIAutomationElement:
        """Convierte un UIAElementInfo en un UIAutomationElement serializable."""
        try:
            rect = info.rectangle
            bbox = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            bbox = (0, 0, 0, 0)

        try:
            runtime = tuple(int(x) for x in (info.runtime_id or ()))
        except Exception:
            runtime = ()

        try:
            control_id = int(info.control_id or 0)
        except Exception:
            control_id = 0

        patterns = self._collect_patterns(info)

        is_offscreen = self._read_offscreen(info)

        raw_framework_id = str(getattr(info, "framework_id", "") or "")
        return UIAutomationElement(
            automation_id=str(info.automation_id or ""),
            name=str(info.name or ""),
            control_type=str(info.control_type or ""),
            class_name=str(info.class_name or ""),
            control_id=control_id,
            bounding_rectangle=bbox,
            process_id=int(info.process_id or (pid or 0)),
            runtime_id=runtime,
            is_enabled=bool(info.enabled),
            is_offscreen=is_offscreen,
            visible=bool(info.visible),
            handle=int(info.handle or 0),
            framework_id=raw_framework_id,
            framework=classify_framework(
                raw_framework_id,
                str(info.class_name or ""),
                str(info.control_type or ""),
            ),
            parent_handle=parent_handle,
            child_count=0,
            patterns=list(patterns),
            depth=depth,
            source="uia",
        )

    def _read_offscreen(self, info: UIAElementInfo) -> bool:
        """Lee IsOffscreen del elemento AutomationElement subyacente (COM).

        UIAElementInfo no expone is_offscreen directamente, asi que se intenta
        leer del elemento AutomationElement crudo. Si no esta disponible, se
        devuelve False (no se asume fuera de pantalla sin evidencia).
        """
        element = getattr(info, "element", None)
        if element is None:
            return False
        try:
            return bool(element.CurrentIsOffscreen)
        except Exception:
            try:
                return bool(element.GetCurrentPropertyValue(
                    uia_defines_property("IsOffscreen")
                ))
            except Exception:
                return False

    def _collect_patterns(self, info: UIAElementInfo) -> List[str]:
        """Devuelve los nombres de los patrones de control soportados.

        Solo consulta disponibilidad; nunca se invocan.
        """
        patterns: List[str] = []
        element = getattr(info, "element", None)
        if element is None:
            return patterns
        for pattern_name in CONTROL_PATTERNS:
            try:
                pattern_id = _pattern_id(pattern_name)
                if pattern_id is None:
                    continue
                pattern = element.GetCurrentPattern(pattern_id)
                if pattern is not None:
                    patterns.append(pattern_name)
            except Exception:
                # Patron no soportado por este control; no es un error
                continue
        return patterns

    # ------------------------------------------------------------------
    # Fallback: acceso directo al elemento AutomationElement (COM)
    # ------------------------------------------------------------------

    def _enumerate_with_automation_element(
        self, hwnd: int, pid: Optional[int], start: float
    ) -> UIAutomationTree:
        """Fallback usando IUIAutomation directamente para obtener el
        elemento raiz de la ventana y sus hijos inmediatos.

        Solo se usa si pywinauto no produjo un arbol usable.
        """
        try:
            import comtypes.client  # type: ignore

            try:
                uia = comtypes.client.CreateObject(
                    "{FF48DBA4-60EF-4201-AA87-54103EEF594E}",
                    interface=comtypes.gen.UIAutomationClient.IUIAutomation,
                )
            except Exception:
                uia = comtypes.client.CreateObject(
                    "UIAutomationCore.IUIAutomation"
                )

            root = uia.ElementFromHandle(hwnd)
            if root is None:
                return UIAutomationTree(
                    window_handle=hwnd,
                    process_id=int(pid or 0),
                    window_title="",
                    window_class="",
                    root_element=UIAutomationElement(),
                    error="IUIAutomation.ElementFromHandle devolvio None",
                    source="com",
                    elapsed_seconds=time.perf_counter() - start,
                )

            tree_walker = uia.ControlViewWalker
            first_child = tree_walker.GetFirstChildElement(root)

            root_elem = self._automation_element_to_dataclass(
                root, depth=0, parent_handle=0, pid=pid, uia=uia
            )
            elements: List[UIAutomationElement] = [root_elem]
            seen_handles: Set[int] = {root_elem.handle} if root_elem.handle else set()

            child = first_child
            depth = 1
            while child is not None and len(elements) < self.max_elements and depth <= self.max_depth:
                try:
                    child_elem = self._automation_element_to_dataclass(
                        child, depth=depth, parent_handle=root_elem.handle,
                        pid=pid, uia=uia,
                    )
                    if child_elem.handle and child_elem.handle in seen_handles:
                        child = tree_walker.GetNextSiblingElement(child)
                        continue
                    if child_elem.handle:
                        seen_handles.add(child_elem.handle)
                    elements.append(child_elem)
                except Exception:
                    pass
                child = tree_walker.GetNextSiblingElement(child)
                depth += 1

            # Salio del bucle por limites (profundidad o cantidad) y aun quedan
            # hermanos por recorrer: el arbol se trato como virtualizado/grande
            # y se trunca intencionalmente para no bloquear la enumeracion.
            truncated = child is not None

            try:
                title = str(root.CurrentName or "")
            except Exception:
                title = ""
            try:
                class_name = str(root.CurrentClassName or "")
            except Exception:
                class_name = ""

            return UIAutomationTree(
                window_handle=hwnd,
                process_id=int(pid or root_elem.process_id or 0),
                window_title=title,
                window_class=class_name,
                root_element=root_elem,
                elements=elements,
                element_count=len(elements),
                truncated=truncated,
                source="com",
                elapsed_seconds=time.perf_counter() - start,
            )
        except Exception as exc:
            logger.debug(
                "[UI-AUTOMATION-ADAPTER] Fallback COM fallo para HWND=%s: %s",
                hwnd,
                exc,
            )
            return UIAutomationTree(
                window_handle=hwnd,
                process_id=int(pid or 0),
                window_title="",
                window_class="",
                root_element=UIAutomationElement(),
                error=str(exc),
                source="com",
                elapsed_seconds=time.perf_counter() - start,
            )

    def _automation_element_to_dataclass(
        self,
        elem: Any,
        depth: int = 0,
        parent_handle: int = 0,
        pid: Optional[int] = None,
        uia: Any = None,
    ) -> UIAutomationElement:
        """Convierte un IUIAutomationElement crudo (COM) en UIAutomationElement."""
        try:
            handle = int(elem.CurrentNativeWindowHandle or 0)
        except Exception:
            handle = 0
        try:
            rect = elem.CurrentBoundingRectangle
            bbox = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            bbox = (0, 0, 0, 0)
        try:
            runtime = tuple(int(x) for x in (elem.CurrentRuntimeId or ()))
        except Exception:
            runtime = ()
        try:
            control_id = int(elem.CurrentControlId or 0)
        except Exception:
            control_id = 0
        try:
            offscreen = bool(elem.CurrentIsOffscreen)
        except Exception:
            offscreen = False
        try:
            enabled = bool(elem.CurrentIsEnabled)
        except Exception:
            enabled = False
        try:
            visible = bool(elem.CurrentIsVisible)
        except Exception:
            visible = False

        patterns = self._collect_patterns_com(elem)

        raw_framework_id = str(elem.CurrentFrameworkId or "")
        return UIAutomationElement(
            automation_id=str(elem.CurrentAutomationId or ""),
            name=str(elem.CurrentName or ""),
            control_type=str(elem.CurrentControlTypeProgrammaticName or ""),
            class_name=str(elem.CurrentClassName or ""),
            control_id=control_id,
            bounding_rectangle=bbox,
            process_id=int(elem.CurrentProcessId or (pid or 0)),
            runtime_id=runtime,
            is_enabled=enabled,
            is_offscreen=offscreen,
            visible=visible,
            handle=handle,
            framework_id=raw_framework_id,
            framework=classify_framework(
                raw_framework_id,
                str(elem.CurrentClassName or ""),
                str(elem.CurrentControlTypeProgrammaticName or ""),
            ),
            parent_handle=parent_handle,
            child_count=0,
            patterns=list(patterns),
            depth=depth,
            source="com",
        )

    def _collect_patterns_com(self, elem: Any) -> List[str]:
        """Consulta patrones de control en un IUIAutomationElement crudo."""
        patterns: List[str] = []
        for pattern_name in CONTROL_PATTERNS:
            try:
                pattern_id = _pattern_id(pattern_name)
                if pattern_id is None:
                    continue
                try:
                    pattern = elem.GetCurrentPattern(pattern_id)
                except Exception:
                    pattern = None
                if pattern is not None:
                    patterns.append(pattern_name)
            except Exception:
                continue
        return patterns

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_text(info: UIAElementInfo, attr: str) -> str:
        try:
            value = getattr(info, attr, None)
            return str(value or "")
        except Exception:
            return ""


def _pattern_id(pattern_name: str) -> Optional[int]:
    """Devuelve el ID numerico de un patron de control UIA, o None."""
    try:
        from pywinauto import uia_defines
        entry = uia_defines.pattern_ids.get(pattern_name)
        if entry is None:
            return None
        return int(entry[0])
    except Exception:
        return None


def uia_defines_property(name: str) -> Any:
    """Devuelve un property ID de UIA por nombre (fallback COM)."""
    try:
        import comtypes.client
        uia = comtypes.client.CreateObject(
            "{FF48DBA4-60EF-4201-AA87-54103EEF594E}",
            interface=comtypes.gen.UIAutomationClient.IUIAutomation,
        )
        return getattr(uia, "PropertyId_" + name, None)
    except Exception:
        return None
