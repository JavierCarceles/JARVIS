"""Modelo can\u00f3nico de elemento de interfaz de usuario (UI Element).

Proporciona una \u00fanica representaci\u00f3n de los elementos UI que unifica
el vocabulario usado por:

* Visi\u00f3n (``src.eyes.vision.vision`` y ``src.eyes.vision.vision_only``): detecci\u00f3n y
  verificaci\u00f3n de elementos sobre capturas de pantalla.
* Conocimiento de aplicaciones (``src.hands.apps.applications_core``): cat\u00e1logo
  declarativo de elementos por aplicaci\u00f3n y capacidad.
* Calibraci\u00f3n (``src.hands.calibration.calibrator`` y
  ``src.hands.calibration.universal_visual_calibrator``): coordenadas calibradas y su estado.
* Ejecuci\u00f3n (``src.hands.actions.executor``): estado de ejecuci\u00f3n de un elemento.

Cada capa puede consumir el subconjunto de atributos que le corresponde; el
modelo can\u00f3nico garantiza nombres de campo y sem\u00e1ntica comunes por
toda la base de c\u00f3digo, evitando las m\u00faltiples representaciones
incompatibles que exist\u00edan con anterioridad (faltaba ``name`` en visi\u00f3n,
``bbox``/``center`` ausentes en conocimiento de aplicaciones, vocabulario
``element_type`` vs ``type`` en calibraci\u00f3n, etc.).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field


def _is_number(value: Any) -> bool:
    """Devuelve ``True`` solo para valores num\u00e9ricos reales (no bool)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_int_list(value: Any, expected_len: int) -> Optional[List[int]]:
    """Normaliza ``value`` a una lista de enteros con longitud exacta."""
    if not isinstance(value, (list, tuple)) or len(value) != expected_len:
        return None
    try:
        return [int(round(float(item))) for item in value]  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Clasificacion de elementos segun la evidencia de interactividad (unidad 3.8.6.3.3.10)
# ---------------------------------------------------------------------------

class ElementClassification(str, Enum):
    """Clasificacion de un elemento UI segun la evidencia de interactividad.

    Solo UIA_ACTIONABLE acredita interactividad verificada (patron de accion
    UIA utilizable, habilitado, visible y dentro de pantalla). Los demas
    valores describen el elemento sin garantizar que se pueda actuar sobre
    el.
    """

    UIA_ACTIONABLE = "uia_actionable"
    VISUAL_INTERACTABLE_CANDIDATE = "visual_interactable_candidate"
    TEXT_LABEL = "text_label"
    CONTAINER = "container"
    STATIC_CONTENT = "static_content"
    OFFSCREEN = "offscreen"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


# Patrones de control UIA que acreditan capacidad de interaccion. Coincide
# con el conjunto usado por ui_automation_adapter y visual_ui_detector_fusion.
CLASSIFICATION_ACTIONABLE_PATTERNS = frozenset({
    "Invoke", "Value", "Toggle", "Selection", "ExpandCollapse",
    "Scroll", "Window", "Transform",
})

# Tipos canonicos que representan un contenedor de otros controles.
CLASSIFICATION_CONTAINER_TYPES = frozenset({"menu", "toolbar"})

# Tipos canonicos con rol interactivo aparente (candidato sin verificar).
CLASSIFICATION_INTERACTIVE_TYPES = frozenset({
    "button", "link", "checkbox", "radio", "input", "address_bar",
    "field", "select",
})


class UIElementData(BaseModel):
    """Representaci\u00f3n can\u00f3nica de un elemento de interfaz de usuario.

    Los atributos est\u00e1n agrupados por origen sem\u00e1ntico:

    * Identidad: ``name``, ``type``, ``description``, ``text``.
    * Geometr\u00eda visual: ``bbox`` (``[x1, y1, x2, y2]``), ``center``
      (``[x, y]``), ``coordinates`` (formato cl\u00e1sico de calibraci\u00f3n
      ``{"x", "y"}`` o multipantalla ``{"s1": [x, y], ...}``), ``screen``.
    * Visibilidad/interacci\u00f3n: ``interactive``, ``confidence``.
    * Calibraci\u00f3n: ``calibrated``, ``calibration_data``,
      ``required_capability``.
    """

    name: str = ""
    type: str = "unknown"
    description: str = ""
    text: str = ""
    bbox: Optional[List[int]] = None
    center: List[int] = Field(default_factory=list)
    coordinates: Optional[Dict[str, Any]] = None
    screen: int = 0
    interactive: bool = True
    confidence: float = 0.0
    calibrated: bool = False
    calibration_data: Optional[Dict[str, Any]] = None
    required_capability: Optional[str] = None
    classification: ElementClassification = ElementClassification.UNKNOWN

    # ------------------------------------------------------------------
    # Consultas semanticas
    # ------------------------------------------------------------------
    def is_calibrated(self) -> bool:
        """Indica si el elemento dispone de coordenadas utilizables.

        Considera tanto la bandera expl\u00edcita ``calibrated`` como la
        presencia de coordenadas en formato cl\u00e1sico o multipantalla,
        manteniendo la sem\u00e1ntica hist\u00f3rica de ``applications_core``.
        """
        if self.calibrated:
            return True
        return self._coordinates_calibrated(self.coordinates)

    @staticmethod
    def _coordinates_calibrated(coordinates: Any) -> bool:
        if not isinstance(coordinates, dict) or not coordinates:
            return False

        # Formato cl\u00e1sico {"x": ..., "y": ...}.
        if "x" in coordinates and "y" in coordinates:
            return _is_number(coordinates.get("x")) and _is_number(coordinates.get("y"))

        # Formato multipantalla {"s1": [x, y], "s2": [x, y], ...}.
        return any(
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and all(_is_number(item) for item in value[:2])
            for key, value in coordinates.items()
            if str(key).lower().startswith("s")
        )

    def has_valid_geometry(self) -> bool:
        """Devuelve ``True`` si el elemento expone geometr\u00eda usable."""
        if self.bbox is not None:
            return len(self.bbox) == 4 and all(_is_number(i) for i in self.bbox)
        if self.center:
            return len(self.center) == 2 and all(_is_number(i) for i in self.center)
        return self.is_calibrated()

    def matches_name(self, name: str) -> bool:
        """Comprueba si el elemento corresponde a ``name`` (por nombre o texto)."""
        target = str(name or "").strip().lower()
        if not target:
            return False
        ours = (self.name or "").strip().lower()
        if ours and ours == target:
            return True
        haystack = f"{self.type} {self.text}".lower()
        return target in haystack

    # ------------------------------------------------------------------
    # Serializaci\u00f3n / construcci\u00f3n
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Devuelve un diccionario serializable con la forma can\u00f3nica."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Any) -> "UIElementData":
        """Construye un elemento can\u00f3nico filtrando claves desconocidas."""
        if not isinstance(data, dict):
            return cls()
        known = {key: value for key, value in data.items() if key in cls.model_fields}
        try:
            return cls(**known)
        except Exception:
            # Si los tipos no encajan exactamente, conserva lo seguro.
            return cls(
                **{
                    k: v
                    for k, v in known.items()
                    if k in {"name", "type", "description", "text", "bbox", "center",
                             "coordinates", "screen", "interactive", "confidence",
                             "calibrated", "calibration_data", "required_capability"}
                }
            )

    @classmethod
    def from_compact_dict(cls, data: Any) -> "UIElementData":
        """Construye desde la respuesta compacta del modelo de visi\u00f3n.

        Formato esperado: ``{name?, type, text, bbox, center, interactive,
        confidence}``. El nombre se infiere de ``text``/``type`` cuando falta.
        """
        if not isinstance(data, dict):
            return cls()
        name = str(
            data.get("name") or data.get("text") or data.get("type") or "element"
        ).strip()
        return cls(
            name=name,
            type=str(data.get("type", "unknown") or "unknown"),
            text=str(data.get("text", "") or ""),
            bbox=_as_int_list(data.get("bbox"), 4),
            center=_as_int_list(data.get("center"), 2) or [],
            interactive=bool(data.get("interactive", True)),
            confidence=float(data.get("confidence", 0.0) or 0.0),
        )

    @staticmethod
    def normalize_name(name: Any) -> str:
        """Normaliza un nombre a clave can\u00f3nica (uso interno/planificador)."""
        return re.sub(
            r"[^a-z0-9]+", "_", str(name or "").strip().lower()
        ).strip("_")


# ---------------------------------------------------------------------------
# Normalizacion de tipos de elemento (Vision -> canonico)
# ---------------------------------------------------------------------------

# Conjunto canonico de tipos de elemento validos para
# ``coordinate_manager.validate_resource_for_action``. Es la union de los
# subconjuntos que esa funcion acepta segun la accion (``focus_``,
# ``click_``, ``type_``), mas el tipo generico ``"element"``. Nunca se
# inventan tipos fuera de este conjunto.
CANONICAL_ELEMENT_TYPES: frozenset[str] = frozenset({
    "input",
    "address_bar",
    "field",
    "text",
    "element",  # generico: aceptado por focus_/click_; rechazado por type_
    "button",
    "link",
    "menu",
    "checkbox",
    "radio",
    "select",
    "toolbar",
})

# Alias de forma libre (variantes ingles/espanol que el LLM de Vision puede
# devolver en D-UI-TYPE-FREE-FORM) -> tipo canonico. Este mapa nunca crea
# tipos nuevos: solo traduce variantes observadas al vocabulario canonico.
_ELEMENT_TYPE_ALIASES: Dict[str, str] = {
    # button
    "button": "button",
    "boton": "button",
    "bot\u00f3n": "button",
    "btn": "button",
    # input
    "input": "input",
    "campo de texto": "input",
    "campo": "field",            # "campo" solo -> field; "campo de texto" -> input
    "entrada": "input",
    "textbox": "input",
    "text input": "input",
    "cuadro de texto": "input",
    # address_bar
    "address_bar": "address_bar",
    "barra de direcciones": "address_bar",
    "address bar": "address_bar",
    "url bar": "address_bar",
    "url_bar": "address_bar",
    # field
    "field": "field",
    # text
    "text": "text",
    "texto": "text",
    # link
    "link": "link",
    "enlace": "link",
    "v\u00ednculo": "link",
    "hiperv\u00ednculo": "link",
    # menu
    "menu": "menu",
    "men\u00fa": "menu",
    # checkbox
    "checkbox": "checkbox",
    "casilla": "checkbox",
    "casilla de verificacion": "checkbox",
    "casilla de verificaci\u00f3n": "checkbox",
    # radio
    "radio": "radio",
    "boton de radio": "radio",
    "bot\u00f3n de radio": "radio",
    # select
    "select": "select",
    "desplegable": "select",
    "lista desplegable": "select",
    "combo": "select",
    # toolbar
    "toolbar": "toolbar",
    "barra de herramientas": "toolbar",
}

# Lookup completo: alias mas cada tipo canonico mapeado a si mismo.
_ELEMENT_TYPE_LOOKUP: Dict[str, str] = dict(_ELEMENT_TYPE_ALIASES)
for _canon in CANONICAL_ELEMENT_TYPES:
    _ELEMENT_TYPE_LOOKUP.setdefault(_canon, _canon)


def normalize_element_type(type_str: Any) -> str:
    """Normaliza un tipo de elemento libre generado por Vision
    (D-UI-TYPE-FREE-FORM) a uno de los tipos canonicos validados por
    ``coordinate_manager.validate_resource_for_action``.

    Nunca inventa tipos nuevos: solo devuelve valores de
    ``CANONICAL_ELEMENT_TYPES``. Un tipo desconocido (o vacio/nulo) se resuelve
    al tipo generico ``"element"``, que el contrato de validacion acepta para
    acciones de enfoque (``focus_``) y clic (``click_``) y rechaza para
    escritura (``type_``), coherente con el comportamiento real de
    ``validate_resource_for_action``.
    """
    if type_str is None:
        return "element"
    key = str(type_str).strip().lower()
    if not key:
        return "element"
    return _ELEMENT_TYPE_LOOKUP.get(key, "element")


def classify_element(
    element: UIElementData,
    uia_patterns: Optional[Iterable[str]] = None,
    enabled: Optional[bool] = None,
    visible: Optional[bool] = None,
    offscreen: Optional[bool] = None,
) -> ElementClassification:
    """Clasifica un elemento segun la evidencia de interactividad disponible.

    Solo se declara interactividad verificada (UIA_ACTIONABLE) cuando hay un
    patron de accion UIA utilizable y el control esta habilitado, visible y
    dentro de pantalla. Un elemento detectado solo visualmente (por ejemplo,
    un icono) queda como VISUAL_INTERACTABLE_CANDIDATE hasta que exista un
    patron UIA o una prueba controlada que demuestre la accion sobre el control.

    Prioridad de decision:
      1. OFFSCREEN: el elemento esta fuera de pantalla.
      2. DISABLED: el control esta deshabilitado.
      3. UIA_ACTIONABLE: patron UIA de accion + habilitado + visible + en pantalla.
      4. TEXT_LABEL: tipo canonico "text".
      5. CONTAINER: tipo canonico "menu" o "toolbar".
      6. STATIC_CONTENT: tipo generico "element" sin rol interactivo.
      7. VISUAL_INTERACTABLE_CANDIDATE: tipo interactivo aparente detectado visualmente, sin verificar.
      8. UNKNOWN: no se pudo clasificar.

    Argumentos:
        element: elemento canonico (se usa su tipo normalizado).
        uia_patterns: patrones de control UIA reportados para el elemento.
        enabled: si el control esta habilitado segun UIA; None = desconocido.
        visible: si el control es visible; None = desconocido.
        offscreen: si el control esta fuera de pantalla; None = desconocido.

    Retorna:
        ElementClassification correspondiente.
    """
    raw_type = str(element.type or "").strip().lower()
    etype = normalize_element_type(element.type)

    offscreen_flag = bool(offscreen) if offscreen is not None else False
    if offscreen_flag:
        return ElementClassification.OFFSCREEN

    enabled_flag = bool(enabled) if enabled is not None else True
    if not enabled_flag:
        return ElementClassification.DISABLED

    visible_flag = bool(visible) if visible is not None else True

    patterns = set(str(p) for p in (uia_patterns or ()))
    if patterns & CLASSIFICATION_ACTIONABLE_PATTERNS:
        if enabled_flag and visible_flag and not offscreen_flag:
            return ElementClassification.UIA_ACTIONABLE

    if etype == "text":
        return ElementClassification.TEXT_LABEL

    if etype in CLASSIFICATION_CONTAINER_TYPES:
        return ElementClassification.CONTAINER

    if etype in CLASSIFICATION_INTERACTIVE_TYPES:
        return ElementClassification.VISUAL_INTERACTABLE_CANDIDATE

    if etype == "element":
        # Tipo generico: puede ser un icono detectado visualmente (candidato
        # sin verificar), un generico explicito (estatico) o un tipo no
        # reconocido (desconocido).
        if raw_type in ("", "unknown"):
            return ElementClassification.UNKNOWN
        if raw_type == "element":
            # Solo se considera candidato interactivo si la deteccion visual
            # lo marco como interactivo y expone geometria utilizable.
            if bool(element.interactive) and element.has_valid_geometry():
                return ElementClassification.VISUAL_INTERACTABLE_CANDIDATE
            return ElementClassification.STATIC_CONTENT
        # normalize devolve "element" como fallback para tipos no reconocidos
        return ElementClassification.UNKNOWN

    return ElementClassification.UNKNOWN


__all__ = [
    "UIElementData",
    "ElementClassification",
    "classify_element",
    "CANONICAL_ELEMENT_TYPES",
    "normalize_element_type",
    "CLASSIFICATION_ACTIONABLE_PATTERNS",
    "CLASSIFICATION_CONTAINER_TYPES",
    "CLASSIFICATION_INTERACTIVE_TYPES",
]
