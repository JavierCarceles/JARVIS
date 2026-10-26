"""Modelo can\u00f3nico de elemento de interfaz de usuario (UI Element).

Proporciona una \u00fanica representaci\u00f3n de los elementos UI que unifica
el vocabulario usado por:

* Visi\u00f3n (``eyes.vision`` y ``eyes.vision_only``): detecci\u00f3n y
  verificaci\u00f3n de elementos sobre capturas de pantalla.
* Conocimiento de aplicaciones (``hands.applications_core``): cat\u00e1logo
  declarativo de elementos por aplicaci\u00f3n y capacidad.
* Calibraci\u00f3n (``hands.calibrator`` y
  ``hands.universal_visual_calibrator``): coordenadas calibradas y su estado.
* Ejecuci\u00f3n (``hands.executor``): estado de ejecuci\u00f3n de un elemento.

Cada capa puede consumir el subconjunto de atributos que le corresponde; el
modelo can\u00f3nico garantiza nombres de campo y sem\u00e1ntica comunes por
toda la base de c\u00f3digo, evitando las m\u00faltiples representaciones
incompatibles que exist\u00edan con anterioridad (faltaba ``name`` en visi\u00f3n,
``bbox``/``center`` ausentes en conocimiento de aplicaciones, vocabulario
``element_type`` vs ``type`` en calibraci\u00f3n, etc.).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

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

    # ------------------------------------------------------------------
    # Consultas semánticas
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


__all__ = ["UIElementData"]
