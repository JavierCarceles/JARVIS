"""
Topologia de monitores y seleccion del monitor destino (Windows y macOS).

Construye un modelo de la topologia real a partir de los monitores que
enumera el contrato de plataforma (``src.desktop.platform_contract``):
geometria absoluta (incluidos origenes negativos y monitores apilados),
resolucion fisica, area util, escala, orientacion y principal. Nunca usa
indices fijos (``DISPLAY2``, orden de conexion, posicion en la lista) ni
dimensiones historicas: ``get_current_topology()`` reenumera siempre.

Piezas:

* ``MonitorTopology``: monitores, relaciones espaciales (izquierda, derecha,
  arriba, abajo, con solape real en el otro eje), orden visual y
  ``fingerprint`` estable e independiente del orden de enumeracion.
* ``resolve_monitor_reference``: resuelve lo que dice el usuario ("la de la
  izquierda", "la grande", "la vertical", "la principal", "la otra", "la 2",
  nombre del monitor) contra la topologia ACTUAL. Si no hay una unica
  respuesta devuelve ``ambiguous`` con candidatos; nunca adivina.
* ``TargetMonitorPolicy``: politica de producto (regla 4 de la cabecera del
  roadmap): usuario -> donde ya esta la aplicacion -> preferencia configurada
  -> monitor de la ventana activa -> monitor del puntero -> principal.
* ``TestMonitorPolicy``: politica de pruebas (regla 5): monitor no principal
  situado mas a la derecha por geometria real; con un solo monitor, ese.
* ``TopologyWatcher``: detecta conexion/desconexion y cambios de escala o
  geometria. Usa el listener del adaptador si existe (WM_DISPLAYCHANGE /
  WM_DPICHANGED en Windows) y, en todo caso, ``check()``/``assert_unchanged()``
  comparan el fingerprint antes de cada accion espacial.

Cubre las unidades 3.8.6.6.1 a 3.8.6.6.5 del roadmap.
"""

from __future__ import annotations

import hashlib
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.core.log import get_logger
from src.desktop.platform_contract import (
    DesktopPlatformAdapter,
    DisplayInfo,
    PlatformError,
    PointerPosition,
    Rect,
    WindowInfo,
    get_desktop_platform,
)

logger = get_logger(__name__)

# Direcciones canonicas de las relaciones espaciales.
DIRECTION_LEFT = "left"
DIRECTION_RIGHT = "right"
DIRECTION_ABOVE = "above"
DIRECTION_BELOW = "below"
DIRECTIONS = (DIRECTION_LEFT, DIRECTION_RIGHT, DIRECTION_ABOVE, DIRECTION_BELOW)

# Tolerancia (unidades de escritorio) para considerar que un monitor empieza
# donde acaba otro. Absorbe redondeos de 1 unidad entre adaptadores.
_EDGE_TOLERANCE = 2.0

# Dos monitores de area "igual" para "el grande"/"el pequeno": diferencia
# relativa menor que este valor se considera empate (ambiguo).
_SIZE_TIE_RATIO = 0.01


class TopologyUnavailableError(RuntimeError):
    """El adaptador no pudo enumerar los monitores reales."""

    def __init__(self, message: str, error: Optional[PlatformError] = None) -> None:
        super().__init__(message)
        self.error = error


# ============================================================================
# MODELO DE TOPOLOGIA
# ============================================================================


def _rect_key(rect: Optional[Rect]) -> Tuple[float, float, float, float]:
    if rect is None:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(round(float(v), 3) for v in rect.to_tuple())  # type: ignore[return-value]


def _display_signature(display: DisplayInfo) -> Tuple[Any, ...]:
    """Datos de un monitor que, si cambian, invalidan geometria calibrada."""
    return (
        str(display.display_id),
        _rect_key(display.bounds),
        int(display.pixel_width),
        int(display.pixel_height),
        round(float(display.scale_factor or 0.0), 4),
        int(display.dpi or 0),
        int(display.rotation or 0),
        bool(display.is_primary),
        str(display.coordinate_space),
    )


def compute_topology_fingerprint(displays: Iterable[DisplayInfo]) -> str:
    """Fingerprint sha256 de una lista de monitores, independiente del orden."""
    signatures = sorted(_display_signature(d) for d in displays)
    raw = "\n".join(repr(sig) for sig in signatures)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _vertical_overlap(a: Rect, b: Rect) -> float:
    return min(a.bottom, b.bottom) - max(a.top, b.top)


def _horizontal_overlap(a: Rect, b: Rect) -> float:
    return min(a.right, b.right) - max(a.left, b.left)


@dataclass
class MonitorTopology:
    """Topologia de monitores en un instante (no se actualiza sola)."""

    displays: List[DisplayInfo] = field(default_factory=list)
    fingerprint: str = ""
    platform: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = compute_topology_fingerprint(self.displays)

    # ------------------------------------------------------------------
    # Construccion
    # ------------------------------------------------------------------

    @classmethod
    def from_displays(
        cls, displays: Iterable[DisplayInfo], platform: str = ""
    ) -> "MonitorTopology":
        valid: List[DisplayInfo] = []
        for display in displays or []:
            if display is None or display.bounds is None or not display.bounds.is_valid():
                logger.warning("Monitor descartado por geometria invalida: %s", getattr(display, "display_id", None))
                continue
            valid.append(display)
        return cls(displays=valid, platform=platform)

    # ------------------------------------------------------------------
    # Consultas basicas
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.displays)

    @property
    def is_empty(self) -> bool:
        return not self.displays

    def get(self, display_id: Optional[str]) -> Optional[DisplayInfo]:
        if display_id is None:
            return None
        key = str(display_id)
        for display in self.displays:
            if str(display.display_id) == key:
                return display
        return None

    def primary(self) -> Optional[DisplayInfo]:
        """Monitor principal declarado por el SO.

        Si ningun monitor esta marcado como principal, se usa el que contiene
        el origen (0, 0) del escritorio (en Windows y en macOS el principal
        tiene origen 0,0). Nunca se toma el primero de la lista por indice.
        """
        for display in self.displays:
            if display.is_primary:
                return display
        origin = self.display_for_point(0, 0)
        if origin is not None:
            return origin
        return None

    def display_for_point(self, x: float, y: float) -> Optional[DisplayInfo]:
        for display in self.displays:
            if display.bounds.contains_point(float(x), float(y)):
                return display
        return None

    def display_for_rect(self, rect: Optional[Rect]) -> Optional[DisplayInfo]:
        """Monitor con mayor area de interseccion con ``rect``."""
        if rect is None or not rect.is_valid():
            return None
        best: Optional[DisplayInfo] = None
        best_area = 0.0
        for display in self.displays:
            area = display.bounds.intersection_area(rect)
            if area > best_area:
                best_area = area
                best = display
        if best is None:
            cx, cy = rect.center
            return self.display_for_point(cx, cy)
        return best

    def display_for_window(self, window: Optional[WindowInfo]) -> Optional[DisplayInfo]:
        """Monitor de una ventana: el que declara el SO o el de mayor interseccion."""
        if window is None:
            return None
        if window.display_id:
            found = self.get(window.display_id)
            if found is not None:
                return found
        rect = window.frame_bounds or window.bounds
        return self.display_for_rect(rect)

    def virtual_bounds(self) -> Optional[Rect]:
        if not self.displays:
            return None
        return Rect(
            min(d.bounds.left for d in self.displays),
            min(d.bounds.top for d in self.displays),
            max(d.bounds.right for d in self.displays),
            max(d.bounds.bottom for d in self.displays),
        )

    # ------------------------------------------------------------------
    # Orden visual y relaciones
    # ------------------------------------------------------------------

    def visual_order(self) -> List[DisplayInfo]:
        """Monitores ordenados de izquierda a derecha y, a igualdad, de arriba a abajo.

        Es el orden que se usa para "la 1", "la 2"... Se calcula por el centro
        geometrico, no por el orden de enumeracion del SO.
        """
        return sorted(
            self.displays,
            key=lambda d: (
                round(d.bounds.center[0], 3),
                round(d.bounds.center[1], 3),
                str(d.display_id),
            ),
        )

    def visual_number(self, display_id: str) -> Optional[int]:
        """Numero visual (1..N) de un monitor segun ``visual_order``."""
        for index, display in enumerate(self.visual_order(), start=1):
            if str(display.display_id) == str(display_id):
                return index
        return None

    @staticmethod
    def _is_in_direction(origin: Rect, other: Rect, direction: str) -> bool:
        if direction == DIRECTION_RIGHT:
            return other.left >= origin.right - _EDGE_TOLERANCE and _vertical_overlap(origin, other) > 0
        if direction == DIRECTION_LEFT:
            return other.right <= origin.left + _EDGE_TOLERANCE and _vertical_overlap(origin, other) > 0
        if direction == DIRECTION_BELOW:
            return other.top >= origin.bottom - _EDGE_TOLERANCE and _horizontal_overlap(origin, other) > 0
        if direction == DIRECTION_ABOVE:
            return other.bottom <= origin.top + _EDGE_TOLERANCE and _horizontal_overlap(origin, other) > 0
        raise ValueError("direccion desconocida: %s" % direction)

    def relations(self, display_id: str) -> Dict[str, List[str]]:
        """Monitores a la izquierda/derecha/arriba/abajo de uno dado.

        Un monitor esta a la derecha de otro si empieza donde el otro acaba (o
        mas alla) y comparten franja vertical (solape real en el otro eje).
        Las listas se ordenan por distancia creciente.
        """
        origin = self.get(display_id)
        result: Dict[str, List[str]] = {d: [] for d in DIRECTIONS}
        if origin is None:
            return result
        for direction in DIRECTIONS:
            found: List[Tuple[float, str]] = []
            for other in self.displays:
                if other is origin:
                    continue
                if self._is_in_direction(origin.bounds, other.bounds, direction):
                    ox, oy = origin.bounds.center
                    cx, cy = other.bounds.center
                    distance = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
                    found.append((distance, str(other.display_id)))
            result[direction] = [display for _, display in sorted(found)]
        return result

    def rightmost_non_primary(self) -> Optional[DisplayInfo]:
        """Monitor no principal con el borde derecho mas a la derecha.

        Empates: mayor centro horizontal y, despues, el de borde superior mas
        alto (desempate geometrico determinista, nunca por indice).
        """
        candidates = [d for d in self.displays if not d.is_primary]
        primary = self.primary()
        if primary is not None:
            candidates = [d for d in candidates if d is not primary]
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda d: (-d.bounds.right, -d.bounds.center[0], d.bounds.top, str(d.display_id)),
        )[0]

    def largest(self) -> List[DisplayInfo]:
        """Monitor(es) de mayor area (empates dentro del 1%)."""
        return _extreme_by_size(self.displays, largest=True)

    def smallest(self) -> List[DisplayInfo]:
        return _extreme_by_size(self.displays, largest=False)

    def portrait_displays(self) -> List[DisplayInfo]:
        return [d for d in self.displays if d.orientation == "portrait"]

    def landscape_displays(self) -> List[DisplayInfo]:
        return [d for d in self.displays if d.orientation == "landscape"]

    def central_displays(self) -> List[DisplayInfo]:
        """Monitores situados en el centro de la disposicion (no extremos en ninguno de los dos ejes).

        Un monitor esta "al centro" cuando no es el mas a la izquierda ni el mas
        a la derecha (dominado en horizontal) ni el mas arriba ni el mas abajo
        (dominado en vertical). Se prioriza el centrado horizontal; si ningun
        monitor cumple, se intenta el centrado vertical. Devuelve la lista de
        monitores centrales (puede haber varios en empate).
        """
        return _middle_candidates(list(self.displays))

    def to_dict(self) -> Dict[str, Any]:
        order = self.visual_order()
        return {
            "fingerprint": self.fingerprint,
            "platform": self.platform,
            "count": len(self.displays),
            "virtual_bounds": self.virtual_bounds().to_dict() if self.virtual_bounds() else None,
            "displays": [
                dict(
                    d.to_dict(),
                    visual_number=order.index(d) + 1,
                    relations=self.relations(str(d.display_id)),
                )
                for d in self.displays
            ],
        }


def _size_key(display: DisplayInfo) -> Tuple[float, float]:
    """Area logica (escritorio) y, como desempate, area en pixeles fisicos.

    El tamano fisico en pulgadas no lo da el SO de forma fiable; "la grande"
    se interpreta como mayor superficie de escritorio.
    """
    return (display.bounds.area, float(display.pixel_width) * float(display.pixel_height))


def _extreme_by_size(displays: Sequence[DisplayInfo], largest: bool) -> List[DisplayInfo]:
    if not displays:
        return []
    keys = [(_size_key(d), d) for d in displays]
    pick = max if largest else min
    best_area = pick(k[0][0] for k in keys)
    tied = [
        (k, d) for k, d in keys
        if best_area > 0 and abs(k[0] - best_area) / best_area <= _SIZE_TIE_RATIO
    ]
    if len(tied) <= 1:
        return [d for _, d in tied] or [keys[0][1]]
    best_pixels = pick(k[1] for k, _ in tied)
    tied_pixels = [
        d for k, d in tied
        if best_pixels > 0 and abs(k[1] - best_pixels) / best_pixels <= _SIZE_TIE_RATIO
    ]
    return tied_pixels or [d for _, d in tied]


def get_current_topology(adapter: Optional[DesktopPlatformAdapter] = None) -> MonitorTopology:
    """Reenumera los monitores reales via el contrato y construye la topologia.

    Nunca reutiliza dimensiones historicas. Levanta ``TopologyUnavailableError``
    si el adaptador no puede enumerar.
    """
    adapter = adapter or get_desktop_platform()
    result = adapter.enumerate_displays()
    if not result.ok:
        message = str(result.error) if result.error else "enumeracion de monitores fallida"
        raise TopologyUnavailableError(message, result.error)
    displays = list(result.value or [])
    if not displays:
        raise TopologyUnavailableError("el SO no devolvio ningun monitor")
    return MonitorTopology.from_displays(displays, platform=getattr(adapter, "platform_name", ""))


# ============================================================================
# REFERENCIAS DEL USUARIO A MONITORES
# ============================================================================


RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"


@dataclass
class MonitorReferenceResult:
    """Resultado de resolver una referencia del usuario a un monitor."""

    status: str
    display: Optional[DisplayInfo] = None
    candidates: List[DisplayInfo] = field(default_factory=list)
    reason: str = ""
    criteria: List[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    @property
    def ambiguous(self) -> bool:
        return self.status == AMBIGUOUS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "display_id": self.display.display_id if self.display else None,
            "candidates": [d.display_id for d in self.candidates],
            "reason": self.reason,
            "criteria": list(self.criteria),
        }


def _normalize_text(text: Any) -> str:
    """Minusculas, sin acentos (NFKD), sin puntuacion y con espacios simples.

    La normalizacion quita las marcas diacriticas, por lo que el vocabulario
    se escribe en ASCII ("pequena" reconoce tambien la forma escrita con enie).
    """
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# Vocabulario (ya normalizado). Incluye variantes de transcripcion mala.
_LEFT_WORDS = ("izquierda", "izquierdo", "isquierda", "isquierdo", "izquierd", "izq",
               "iskierda", "izquierta", "left")
_RIGHT_WORDS = ("derecha", "derecho", "drecha", "derecja", "dereha", "right")
_ABOVE_WORDS = ("arriba", "ariba", "encima", "superior", "de arriba", "top", "upper", "above")
_BELOW_WORDS = ("abajo", "debajo", "inferior", "avajo", "bottom", "lower", "below")
_CENTER_WORDS = ("centro", "central", "medio", "middle", "center", "centre")
_LARGE_WORDS = ("grande", "mas grande", "mayor", "gran", "grandota", "big", "bigger", "largest", "large")
_SMALL_WORDS = ("pequena", "pequeno", "pequenia", "pequenio", "chica", "chico", "menor",
                "mas pequena", "mas chica", "small", "smaller", "smallest")
_PORTRAIT_WORDS = ("vertical", "girada", "girado", "rotada", "rotado", "portrait", "de pie")
_LANDSCAPE_WORDS = ("horizontal", "apaisada", "apaisado", "landscape")
_PRIMARY_WORDS = ("principal", "primaria", "primario", "main", "primary", "prinsipal", "pincipal")
_SECONDARY_WORDS = ("secundaria", "secundario", "secondary", "segundaria")
_OTHER_WORDS = ("otra", "otro", "other", "la otra", "el otro")
# "esta" suelto no basta: "la que esta a la derecha" usa el verbo estar.
_CURRENT_WORDS = ("esta pantalla", "este monitor", "esta misma", "este mismo", "la misma",
                  "el mismo", "la actual", "el actual", "pantalla actual", "monitor actual",
                  "en esta", "en este", "aqui", "current", "this screen", "this monitor")
_RELATIVE_MARKERS = ("de esta", "de este", "de la actual", "del actual", "de donde",
                     "de la que", "del que", "junto a", "al lado", "contigua", "contiguo",
                     "siguiente", "next to")
_NEGATED_PRIMARY = re.compile(r"\bno (?:es |sea )?(?:la |el )?(?:pantalla |monitor )?(?:principal|primaria|primario|main)\b")

_NUMBER_WORDS = {
    "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "one": 1, "two": 2, "three": 3, "four": 4,
}
_ORDINAL_WORDS = {
    "primer": 1, "primera": 1, "primero": 1, "segunda": 2, "segundo": 2,
    "tercer": 3, "tercera": 3, "tercero": 3, "cuarta": 4, "cuarto": 4,
    "quinta": 5, "quinto": 5, "first": 1, "second": 2, "third": 3, "fourth": 4,
}
_NUMBER_NOUNS = r"(?:pantalla|monitor|display|screen|numero|la|el|n)"
_DIGIT_PATTERN = re.compile(r"\b" + _NUMBER_NOUNS + r"\s*(?:numero\s*)?(\d{1,2})\b")
_WORD_NUMBER_PATTERN = re.compile(
    r"\b" + _NUMBER_NOUNS + r"\s+(?:numero\s+)?(" + "|".join(_NUMBER_WORDS) + r")\b"
)
_ORDINAL_PATTERN = re.compile(r"\b(" + "|".join(_ORDINAL_WORDS) + r")\b")

# Palabras genericas que no identifican un monitor por su nombre.
_GENERIC_NAME_TOKENS = frozenset({
    "monitor", "display", "pantalla", "screen", "generic", "generico", "pnp",
    "built", "builtin", "integrated", "the", "and", "con", "del", "las", "los",
})


def _contains_phrase(norm: str, phrases: Sequence[str]) -> bool:
    padded = " %s " % norm
    for phrase in phrases:
        if " %s " % phrase in padded:
            return True
    return False


def _parse_number(norm: str) -> Optional[int]:
    match = _DIGIT_PATTERN.search(norm)
    if match:
        return int(match.group(1))
    match = _WORD_NUMBER_PATTERN.search(norm)
    if match:
        return _NUMBER_WORDS.get(match.group(1))
    match = _ORDINAL_PATTERN.search(norm)
    if match:
        return _ORDINAL_WORDS.get(match.group(1))
    return None


def _name_tokens(display: DisplayInfo) -> List[str]:
    tokens = _normalize_text(display.name).split()
    return [t for t in tokens if len(t) >= 3 and not t.isdigit() and t not in _GENERIC_NAME_TOKENS]


def _dominated(display: DisplayInfo, others: Sequence[DisplayInfo], direction: str) -> bool:
    """True si otro candidato esta claramente mas hacia ``direction``.

    "Claramente" = su centro esta desplazado en esa direccion mas de la mitad
    del menor de los dos monitores en ese eje. Asi un monitor en diagonal
    tambien queda dominado, un monitor vertical muy alto no "gana" arriba a uno
    situado encima del principal y dos monitores en la misma columna o fila
    empatan (ambiguedad real).
    """
    box = display.bounds
    dx, dy = box.center
    for other in others:
        if other is display:
            continue
        ob = other.bounds
        cx, cy = ob.center
        half_w = min(box.width, ob.width) / 2.0
        half_h = min(box.height, ob.height) / 2.0
        if direction == DIRECTION_LEFT and cx < dx - half_w:
            return True
        if direction == DIRECTION_RIGHT and cx > dx + half_w:
            return True
        if direction == DIRECTION_ABOVE and cy < dy - half_h:
            return True
        if direction == DIRECTION_BELOW and cy > dy + half_h:
            return True
    return False


def _nearest_to(origin: DisplayInfo, candidates: List[DisplayInfo]) -> List[DisplayInfo]:
    """Candidatos a menor distancia entre centros del monitor ``origin`` (empates incluidos)."""
    if len(candidates) <= 1:
        return list(candidates)
    ox, oy = origin.bounds.center

    def _dist(d: DisplayInfo) -> float:
        cx, cy = d.bounds.center
        return ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5

    best = min(_dist(d) for d in candidates)
    return [d for d in candidates if _dist(d) - best <= _EDGE_TOLERANCE]


def _extreme_in_direction(candidates: List[DisplayInfo], direction: str) -> List[DisplayInfo]:
    return [d for d in candidates if not _dominated(d, candidates, direction)]


def _middle_candidates(candidates: List[DisplayInfo]) -> List[DisplayInfo]:
    horizontal = [
        d for d in candidates
        if _dominated(d, candidates, DIRECTION_LEFT) and _dominated(d, candidates, DIRECTION_RIGHT)
    ]
    if horizontal:
        return horizontal
    return [
        d for d in candidates
        if _dominated(d, candidates, DIRECTION_ABOVE) and _dominated(d, candidates, DIRECTION_BELOW)
    ]


def resolve_monitor_reference(
    text: str,
    topology: MonitorTopology,
    current_display_id: Optional[str] = None,
) -> MonitorReferenceResult:
    """Resuelve una referencia hablada a un monitor contra la topologia actual.

    Reconoce (en espanol, con acentos o sin ellos y variantes de mala
    transcripcion): direccion ("izquierda", "derecha", "arriba", "abajo",
    combinables: "arriba a la derecha"), "centro", "grande"/"pequena",
    "vertical"/"horizontal", "principal", "secundaria", "la otra", "esta"/
    "la actual", numero ("la 2", "pantalla dos", "la segunda") y nombre del
    monitor. Relativas al monitor actual: "a la izquierda de esta", "la de al
    lado", "la siguiente" (requieren ``current_display_id``).

    Numeracion: "la N" es el N-esimo monitor en orden visual (de izquierda a
    derecha y, en la misma columna, de arriba a abajo), NO el indice de
    enumeracion del SO.

    Orden de aplicacion de criterios: nombre, numero, actual, principal/
    secundaria/otra, orientacion, direccion, centro y tamano. Si al final
    queda mas de un candidato el resultado es ``ambiguous`` con candidatos;
    si ninguno, ``not_found`` con el motivo. Nunca adivina.
    """
    displays = list(topology.displays)
    if not displays:
        return MonitorReferenceResult(NOT_FOUND, reason="no hay monitores enumerados")
    norm = _normalize_text(text)
    if not norm:
        return MonitorReferenceResult(NOT_FOUND, reason="referencia vacia")

    candidates: List[DisplayInfo] = list(displays)
    criteria: List[str] = []
    current = topology.get(current_display_id) if current_display_id else None

    def _fail(reason: str) -> MonitorReferenceResult:
        return MonitorReferenceResult(NOT_FOUND, None, [], reason, criteria)

    # 1. Nombre del monitor.
    tokens = set(norm.split())
    by_name = [d for d in candidates if any(t in tokens for t in _name_tokens(d))]
    if by_name:
        candidates = by_name
        criteria.append("nombre")

    # 2. Numero visual.
    number = _parse_number(norm)
    if number is not None:
        criteria.append("numero:%d" % number)
        order = topology.visual_order()
        if number < 1 or number > len(order):
            return _fail("no existe el monitor %d (hay %d)" % (number, len(order)))
        wanted = order[number - 1]
        candidates = [d for d in candidates if d is wanted]
        if not candidates:
            return _fail("el monitor %d no cumple el resto de la referencia" % number)

    relative = current is not None and _contains_phrase(norm, _RELATIVE_MARKERS)

    # 3. Monitor actual ("esta", "la actual"), salvo uso relativo ("a la izquierda de esta").
    if not relative and _contains_phrase(norm, _CURRENT_WORDS) and not _contains_phrase(norm, _OTHER_WORDS):
        criteria.append("actual")
        if current is None:
            return _fail("no se conoce el monitor actual para resolver 'esta'")
        candidates = [d for d in candidates if d is current]
        if not candidates:
            return _fail("el monitor actual no cumple el resto de la referencia")

    # 4. Principal / secundaria / otra.
    negated_primary = bool(_NEGATED_PRIMARY.search(norm))
    if _contains_phrase(norm, _PRIMARY_WORDS) and not negated_primary:
        criteria.append("principal")
        candidates = [d for d in candidates if d is topology.primary()]
        if not candidates:
            return _fail("ningun monitor principal cumple la referencia")
    elif negated_primary or _contains_phrase(norm, _SECONDARY_WORDS):
        criteria.append("secundaria")
        primary = topology.primary()
        candidates = [d for d in candidates if d is not primary]
        if not candidates:
            return _fail("no hay monitor secundario")
    elif _contains_phrase(norm, _OTHER_WORDS):
        if current is not None:
            criteria.append("otra_que_actual")
            candidates = [d for d in candidates if d is not current]
        else:
            criteria.append("otra_que_principal")
            primary = topology.primary()
            candidates = [d for d in candidates if d is not primary]
        if not candidates:
            return _fail("no hay otro monitor")

    # 5. Orientacion.
    if _contains_phrase(norm, _PORTRAIT_WORDS):
        criteria.append("vertical")
        candidates = [d for d in candidates if d.orientation == "portrait"]
        if not candidates:
            return _fail("no hay ningun monitor vertical")
    elif _contains_phrase(norm, _LANDSCAPE_WORDS):
        criteria.append("horizontal")
        candidates = [d for d in candidates if d.orientation == "landscape"]
        if not candidates:
            return _fail("no hay ningun monitor horizontal")

    # 6. Direccion (absoluta o relativa al monitor actual).
    wanted_directions: List[str] = []
    if _contains_phrase(norm, _LEFT_WORDS):
        wanted_directions.append(DIRECTION_LEFT)
    if _contains_phrase(norm, _RIGHT_WORDS):
        wanted_directions.append(DIRECTION_RIGHT)
    if _contains_phrase(norm, _ABOVE_WORDS):
        wanted_directions.append(DIRECTION_ABOVE)
    if _contains_phrase(norm, _BELOW_WORDS):
        wanted_directions.append(DIRECTION_BELOW)
    if DIRECTION_LEFT in wanted_directions and DIRECTION_RIGHT in wanted_directions:
        return _fail("la referencia pide izquierda y derecha a la vez")
    if DIRECTION_ABOVE in wanted_directions and DIRECTION_BELOW in wanted_directions:
        return _fail("la referencia pide arriba y abajo a la vez")

    if relative and current is not None:
        rel = topology.relations(str(current.display_id))
        if wanted_directions:
            for direction in wanted_directions:
                criteria.append("relativa:%s" % direction)
                allowed = set(rel[direction])
                candidates = [d for d in candidates if str(d.display_id) in allowed]
            if not candidates:
                return _fail("no hay monitor en esa direccion respecto al actual")
            # "a la izquierda de esta" = el vecino mas cercano en esa direccion;
            # empate de distancia -> ambiguo.
            candidates = _nearest_to(current, candidates)
        else:
            # "la de al lado", "la siguiente": cualquier vecino del actual.
            criteria.append("relativa:vecino")
            neighbours = set()
            for direction in DIRECTIONS:
                neighbours.update(rel[direction])
            candidates = [d for d in candidates if str(d.display_id) in neighbours]
            if not candidates:
                return _fail("el monitor actual no tiene vecinos")
    else:
        for direction in wanted_directions:
            criteria.append(direction)
            candidates = _extreme_in_direction(candidates, direction)

    # 7. Centro.
    if _contains_phrase(norm, _CENTER_WORDS):
        criteria.append("centro")
        middle = _middle_candidates(candidates)
        if middle:
            candidates = middle
        elif len(candidates) > 1:
            return MonitorReferenceResult(
                AMBIGUOUS, None, list(candidates),
                "no hay un monitor central unico en esta disposicion", criteria,
            )

    # 8. Tamano.
    if _contains_phrase(norm, _LARGE_WORDS):
        criteria.append("grande")
        candidates = _extreme_by_size(candidates, largest=True)
    elif _contains_phrase(norm, _SMALL_WORDS):
        criteria.append("pequena")
        candidates = _extreme_by_size(candidates, largest=False)

    if not criteria:
        return MonitorReferenceResult(
            NOT_FOUND, None, [], "referencia a monitor no reconocida: %r" % norm, criteria
        )
    if not candidates:
        return _fail("ningun monitor cumple: %s" % ", ".join(criteria))
    if len(candidates) == 1:
        reason = "resuelto por %s" % ", ".join(criteria)
        if len(displays) == 1:
            reason += " (solo existe un monitor)"
        return MonitorReferenceResult(RESOLVED, candidates[0], list(candidates), reason, criteria)
    return MonitorReferenceResult(
        AMBIGUOUS,
        None,
        list(candidates),
        "%d monitores cumplen %s; hay que preguntar" % (len(candidates), ", ".join(criteria)),
        criteria,
    )


# ============================================================================
# POLITICAS DE MONITOR DESTINO
# ============================================================================


@dataclass
class MonitorSelection:
    """Monitor elegido por una politica, con su origen y motivo."""

    display: Optional[DisplayInfo]
    source: str
    reason: str
    ambiguous: bool = False
    candidates: List[DisplayInfo] = field(default_factory=list)
    topology_fingerprint: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.display is not None and not self.ambiguous

    def to_dict(self) -> Dict[str, Any]:
        return {
            "display_id": self.display.display_id if self.display else None,
            "source": self.source,
            "reason": self.reason,
            "ambiguous": self.ambiguous,
            "candidates": [d.display_id for d in self.candidates],
            "topology_fingerprint": self.topology_fingerprint,
            "notes": list(self.notes),
        }


# Pasos de la politica de producto (regla 4 de la cabecera del roadmap).
STEP_USER = "user"
STEP_APP_CURRENT = "app_current"
STEP_CONFIGURED = "configured_preference"
STEP_ACTIVE_WINDOW = "active_window"
STEP_POINTER = "pointer"
STEP_PRIMARY = "primary"

DEFAULT_PRODUCT_ORDER = (
    STEP_USER,
    STEP_APP_CURRENT,
    STEP_CONFIGURED,
    STEP_ACTIVE_WINDOW,
    STEP_POINTER,
    STEP_PRIMARY,
)


class TargetMonitorPolicy:
    """Politica de PRODUCTO para elegir el monitor de una aplicacion.

    Orden por defecto (configurable con ``order``): (1) el monitor que pide el
    usuario, resuelto contra la topologia actual (si es ambiguo, se devuelve
    ``ambiguous`` para preguntar; si no existe, se devuelve sin monitor y NO se
    sustituye por otro); (2) si la aplicacion ya esta abierta, donde esta;
    (3) preferencia configurada por el usuario (por ``display_id``); (4) monitor
    de la ventana activa; (5) monitor del puntero; (6) principal.

    La peticion explicita del usuario se evalua siempre primero aunque el
    orden configurado la coloque en otro lugar.
    """

    def __init__(
        self,
        order: Sequence[str] = DEFAULT_PRODUCT_ORDER,
        allow_primary_fallback: bool = True,
    ) -> None:
        steps = [s for s in order if s in DEFAULT_PRODUCT_ORDER]
        if STEP_USER in steps:
            steps.remove(STEP_USER)
        self.order: Tuple[str, ...] = tuple([STEP_USER] + steps)
        self.allow_primary_fallback = bool(allow_primary_fallback)

    def select(
        self,
        topology: MonitorTopology,
        user_reference: Optional[str] = None,
        window: Optional[WindowInfo] = None,
        configured_display_id: Optional[str] = None,
        active_window: Optional[WindowInfo] = None,
        pointer: Optional[PointerPosition] = None,
        current_display_id: Optional[str] = None,
    ) -> MonitorSelection:
        fingerprint = topology.fingerprint
        notes: List[str] = []
        if topology.is_empty:
            return MonitorSelection(None, "none", "no hay monitores", topology_fingerprint=fingerprint)

        for step in self.order:
            if step == STEP_USER:
                if user_reference is None or not str(user_reference).strip():
                    continue
                current = current_display_id
                if current is None and window is not None:
                    win_display = topology.display_for_window(window)
                    current = str(win_display.display_id) if win_display else None
                ref = resolve_monitor_reference(user_reference, topology, current_display_id=current)
                if ref.resolved:
                    return MonitorSelection(ref.display, STEP_USER, ref.reason,
                                            topology_fingerprint=fingerprint, notes=notes)
                if ref.ambiguous:
                    return MonitorSelection(None, STEP_USER, ref.reason, True, list(ref.candidates),
                                            topology_fingerprint=fingerprint, notes=notes)
                return MonitorSelection(None, STEP_USER, ref.reason,
                                        topology_fingerprint=fingerprint, notes=notes)
            if step == STEP_APP_CURRENT and window is not None:
                display = topology.display_for_window(window)
                if display is not None:
                    return MonitorSelection(display, STEP_APP_CURRENT,
                                            "la aplicacion ya esta abierta en este monitor",
                                            topology_fingerprint=fingerprint, notes=notes)
                notes.append("ventana de la aplicacion fuera de los monitores actuales")
            if step == STEP_CONFIGURED and configured_display_id:
                display = topology.get(configured_display_id)
                if display is not None:
                    return MonitorSelection(display, STEP_CONFIGURED, "preferencia configurada por el usuario",
                                            topology_fingerprint=fingerprint, notes=notes)
                notes.append("el monitor preferido %s no esta conectado" % configured_display_id)
            if step == STEP_ACTIVE_WINDOW and active_window is not None:
                display = topology.display_for_window(active_window)
                if display is not None:
                    return MonitorSelection(display, STEP_ACTIVE_WINDOW, "monitor de la ventana activa",
                                            topology_fingerprint=fingerprint, notes=notes)
            if step == STEP_POINTER and pointer is not None:
                display = topology.display_for_point(pointer.x, pointer.y)
                if display is not None:
                    return MonitorSelection(display, STEP_POINTER, "monitor del puntero",
                                            topology_fingerprint=fingerprint, notes=notes)
            if step == STEP_PRIMARY and self.allow_primary_fallback:
                display = topology.primary()
                if display is not None:
                    return MonitorSelection(display, STEP_PRIMARY, "monitor principal (ultimo recurso)",
                                            topology_fingerprint=fingerprint, notes=notes)
        return MonitorSelection(None, "none", "ninguna regla de la politica eligio monitor",
                                topology_fingerprint=fingerprint, notes=notes)


class TestMonitorPolicy:
    """Politica de PRUEBAS GUI (regla 5 de la cabecera del roadmap).

    Elige el monitor no principal situado mas a la derecha segun la geometria
    real (borde derecho; desempate por centro y borde superior). Con un solo
    monitor elige ese y lo anota (cobertura de un monitor). ``side="left"``
    permite la variante simetrica si alguna vez se configura.
    """

    __test__ = False  # evita que pytest la recoja como clase de test

    def __init__(self, side: str = "right", prefer_non_primary: bool = True) -> None:
        if side not in ("right", "left"):
            raise ValueError("side debe ser 'right' o 'left'")
        self.side = side
        self.prefer_non_primary = bool(prefer_non_primary)

    def select(self, topology: MonitorTopology) -> MonitorSelection:
        fingerprint = topology.fingerprint
        if topology.is_empty:
            return MonitorSelection(None, "none", "no hay monitores", topology_fingerprint=fingerprint)
        if len(topology.displays) == 1:
            return MonitorSelection(topology.displays[0], "single",
                                    "solo hay un monitor: cobertura de un monitor",
                                    topology_fingerprint=fingerprint)
        primary = topology.primary()
        pool = list(topology.displays)
        if self.prefer_non_primary:
            non_primary = [d for d in pool if d is not primary and not d.is_primary]
            pool = non_primary or pool
        if self.side == "right":
            ordered = sorted(pool, key=lambda d: (-d.bounds.right, -d.bounds.center[0], d.bounds.top, str(d.display_id)))
            reason = "monitor no principal mas a la derecha por geometria real"
        else:
            ordered = sorted(pool, key=lambda d: (d.bounds.left, d.bounds.center[0], d.bounds.top, str(d.display_id)))
            reason = "monitor no principal mas a la izquierda por geometria real"
        return MonitorSelection(ordered[0], "test_policy", reason, topology_fingerprint=fingerprint)


# ============================================================================
# DETECCION DE CAMBIOS DE TOPOLOGIA
# ============================================================================


@dataclass
class TopologyChange:
    """Diferencias entre dos topologias."""

    changed: bool
    previous_fingerprint: str
    current_fingerprint: str
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    modified: Dict[str, List[str]] = field(default_factory=dict)
    events: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "changed": self.changed,
            "previous_fingerprint": self.previous_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "added": list(self.added),
            "removed": list(self.removed),
            "modified": {k: list(v) for k, v in self.modified.items()},
            "events": list(self.events),
            "error": self.error,
        }


def diff_topologies(previous: MonitorTopology, current: MonitorTopology) -> TopologyChange:
    """Compara dos topologias monitor a monitor."""
    prev_map = {str(d.display_id): d for d in previous.displays}
    cur_map = {str(d.display_id): d for d in current.displays}
    added = sorted(set(cur_map) - set(prev_map))
    removed = sorted(set(prev_map) - set(cur_map))
    modified: Dict[str, List[str]] = {}
    for display_id in sorted(set(prev_map) & set(cur_map)):
        a = prev_map[display_id]
        b = cur_map[display_id]
        fields: List[str] = []
        if _rect_key(a.bounds) != _rect_key(b.bounds):
            fields.append("bounds")
        if _rect_key(a.work_area) != _rect_key(b.work_area):
            fields.append("work_area")
        if (a.pixel_width, a.pixel_height) != (b.pixel_width, b.pixel_height):
            fields.append("pixel_size")
        if round(float(a.scale_factor or 0), 4) != round(float(b.scale_factor or 0), 4):
            fields.append("scale_factor")
        if int(a.dpi or 0) != int(b.dpi or 0):
            fields.append("dpi")
        if int(a.rotation or 0) != int(b.rotation or 0):
            fields.append("rotation")
        if bool(a.is_primary) != bool(b.is_primary):
            fields.append("is_primary")
        if fields:
            modified[display_id] = fields
    changed = previous.fingerprint != current.fingerprint or bool(added or removed or modified)
    return TopologyChange(
        changed=changed,
        previous_fingerprint=previous.fingerprint,
        current_fingerprint=current.fingerprint,
        added=added,
        removed=removed,
        modified=modified,
    )


class TopologyWatcher:
    """Vigila la topologia de monitores.

    * ``baseline()`` fija la topologia de referencia (reenumerando).
    * ``check()`` reenumera y compara con la referencia; incluye los eventos
      recibidos del SO desde la ultima comprobacion.
    * ``assert_unchanged(fingerprint)`` es la comprobacion obligatoria antes
      de cada accion espacial (mover, capturar para calibrar, mover puntero).
    * ``start(callback)`` usa ``start_display_change_listener`` del adaptador
      si existe (Windows: WM_DISPLAYCHANGE/WM_DPICHANGED). Si el adaptador no
      lo soporta (macOS por defecto) devuelve False y no crea hilos: el
      consumidor debe llamar ``check()`` antes de cada accion espacial.
    """

    def __init__(self, adapter: Optional[DesktopPlatformAdapter] = None) -> None:
        self._adapter = adapter
        self._baseline: Optional[MonitorTopology] = None
        self._events: List[str] = []
        self._lock = threading.Lock()
        self._listener_handle: Any = None
        self._callback: Optional[Callable[[str], None]] = None

    @property
    def adapter(self) -> DesktopPlatformAdapter:
        if self._adapter is None:
            self._adapter = get_desktop_platform()
        return self._adapter

    @property
    def listening(self) -> bool:
        return self._listener_handle is not None

    @property
    def current_baseline(self) -> Optional[MonitorTopology]:
        return self._baseline

    def baseline(self) -> MonitorTopology:
        topology = get_current_topology(self.adapter)
        with self._lock:
            self._baseline = topology
            self._events = []
        return topology

    def pending_events(self) -> List[str]:
        with self._lock:
            return list(self._events)

    def check(self, update_baseline: bool = False) -> TopologyChange:
        with self._lock:
            events = list(self._events)
            previous = self._baseline
        try:
            current = get_current_topology(self.adapter)
        except TopologyUnavailableError as exc:
            return TopologyChange(
                changed=True,
                previous_fingerprint=previous.fingerprint if previous else "",
                current_fingerprint="",
                events=events,
                error=str(exc),
            )
        if previous is None:
            with self._lock:
                self._baseline = current
                self._events = []
            return TopologyChange(False, current.fingerprint, current.fingerprint, events=events)
        change = diff_topologies(previous, current)
        change.events = events
        if change.changed:
            logger.info(
                "Topologia de monitores cambiada: anadidos=%s quitados=%s modificados=%s eventos=%s",
                change.added, change.removed, change.modified, events,
            )
        if update_baseline:
            with self._lock:
                self._baseline = current
                self._events = []
        return change

    def assert_unchanged(self, fingerprint: str) -> bool:
        """True solo si la topologia actual tiene exactamente ese fingerprint."""
        try:
            current = get_current_topology(self.adapter)
        except TopologyUnavailableError as exc:
            logger.warning("No se pudo comprobar la topologia antes de la accion: %s", exc)
            return False
        if current.fingerprint != fingerprint:
            logger.warning("La topologia cambio entre la deteccion y la accion espacial")
            return False
        return True

    def _on_event(self, reason: str) -> None:
        with self._lock:
            self._events.append(str(reason))
        callback = self._callback
        if callback is not None:
            try:
                callback(str(reason))
            except Exception as exc:
                logger.warning("Callback de cambio de topologia fallo: %s", exc)

    def start(self, callback: Optional[Callable[[str], None]] = None) -> bool:
        """Activa el listener del SO si existe. Devuelve si quedo activo."""
        self._callback = callback
        if self._listener_handle is not None:
            return True
        result = self.adapter.start_display_change_listener(self._on_event)
        if not result.ok:
            logger.debug(
                "Listener de cambios de pantalla no disponible (%s); se usara check() por fingerprint",
                result.error,
            )
            return False
        self._listener_handle = result.value
        return True

    def stop(self) -> None:
        handle = self._listener_handle
        self._listener_handle = None
        if handle is None:
            return
        result = self.adapter.stop_display_change_listener(handle)
        if not result.ok:
            logger.warning("No se pudo detener el listener de pantallas: %s", result.error)


__all__ = [
    "DIRECTIONS",
    "DIRECTION_LEFT",
    "DIRECTION_RIGHT",
    "DIRECTION_ABOVE",
    "DIRECTION_BELOW",
    "RESOLVED",
    "AMBIGUOUS",
    "NOT_FOUND",
    "TopologyUnavailableError",
    "MonitorTopology",
    "compute_topology_fingerprint",
    "get_current_topology",
    "MonitorReferenceResult",
    "resolve_monitor_reference",
    "MonitorSelection",
    "TargetMonitorPolicy",
    "TestMonitorPolicy",
    "DEFAULT_PRODUCT_ORDER",
    "TopologyChange",
    "diff_topologies",
    "TopologyWatcher",
]
