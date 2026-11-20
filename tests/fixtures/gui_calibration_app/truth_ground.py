# -*- coding: ascii -*-
"""
Verdad-terreno de la fixture de calibracion GUI.

Provee la referencia geometrica y el recuento de acciones de cada control.
La instancia se serializa a JSON en runtime/ al lanzar la aplicacion y el
recuento de acciones se actualiza en cada interaccion instrumentada.

Este canal es separado y no lo consume el detector evaluado (ver unidad
3.8.6.10.2): el detector debe llegar a las mismas conclusiones solo por
accesibilidad/vision/fusion sobre la ventana, sin leer este archivo.

Para la matriz controlada (3.8.6.10.4) la geometria puede escalarse por un
factor de zoom interno e incluir opcionalmente el control dinamico.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .controls import CONTROL_SPECS, CONTROL_DINAMICO_SPEC, TAMANIO_NOMINAL

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
TRUTH_GROUND_PATH = os.path.join(_RUNTIME_DIR, "truth_ground.json")
ACTION_COUNTS_PATH = os.path.join(_RUNTIME_DIR, "action_counts.json")


@dataclass
class TruthGround:
    """Referencia geometrica y metadatos de cada control de la fixture."""

    tamanio_ventana: List[int]
    controles: List[Dict[str, Any]]
    controles_sin_accesibilidad: List[str]

    def a_dict(self) -> Dict[str, Any]:
        return {
            "tamanio_ventana": list(self.tamanio_ventana),
            "controles": [
                {
                    "id": c["id"],
                    "kind": c["kind"],
                    "label": c["label"],
                    "geometry": list(c["geometry"]) if c["geometry"] is not None else None,
                    "action": c["action"],
                }
                for c in self.controles
            ],
            "controles_sin_accesibilidad": list(self.controles_sin_accesibilidad),
        }


def _escalar_geometria(geo: Optional[List[int]], factor: float) -> Optional[List[int]]:
    """Escala una geometria [x, y, ancho, alto] por ``factor`` (zoom interno)."""
    if geo is None:
        return None
    return [int(round(v * factor)) for v in geo]


def construir_truth_ground(
    zoom_interno: float = 1.0,
    incluir_dinamico: bool = False,
) -> TruthGround:
    """Construye la verdad-terreno a partir de CONTROL_SPECS.

    ``zoom_interno`` escala las geometrias de referencia para que coincidan
    con los controles reales cuando la fixture aplica un zoom interno.
    ``incluir_dinamico`` anade el control dinamico opcional a la referencia.
    """
    controles = []
    for item in CONTROL_SPECS:
        controles.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "label": item["label"],
                "geometry": _escalar_geometria(item["geometry"], zoom_interno),
                "action": item["action"],
            }
        )
    if incluir_dinamico:
        dinamico = dict(CONTROL_DINAMICO_SPEC)
        dinamico["geometry"] = _escalar_geometria(dinamico.get("geometry"), zoom_interno)
        controles.append(dinamico)
    return TruthGround(
        tamanio_ventana=list(TAMANIO_NOMINAL),
        controles=controles,
        controles_sin_accesibilidad=["canvas_mano"],
    )


def asegurar_runtime_dir() -> None:
    """Crea el directorio de runtime si no existe."""
    os.makedirs(_RUNTIME_DIR, exist_ok=True)


def escribir_truth_ground(zoom_interno: float = 1.0, incluir_dinamico: bool = False) -> None:
    """Persiste la verdad-terreno de referencia en runtime/truth_ground.json."""
    asegurar_runtime_dir()
    datos = construir_truth_ground(zoom_interno=zoom_interno, incluir_dinamico=incluir_dinamico).a_dict()
    with open(TRUTH_GROUND_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=True, indent=2)


def escribir_action_counts(acciones: Dict[str, int]) -> None:
    """Persiste el recuento actual de acciones en runtime/action_counts.json."""
    asegurar_runtime_dir()
    datos = {accion: int(acciones.get(accion, 0)) for accion in sorted(acciones)}
    with open(ACTION_COUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=True, indent=2)


def leer_action_counts() -> Dict[str, int]:
    """Lee el recuento de acciones si el archivo existe."""
    if not os.path.exists(ACTION_COUNTS_PATH):
        return {}
    try:
        with open(ACTION_COUNTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def get_truth_ground(zoom_interno: float = 1.0, incluir_dinamico: bool = False) -> Dict[str, Any]:
    """Devuelve la verdad-terreno como diccionario (canal separado)."""
    return construir_truth_ground(zoom_interno=zoom_interno, incluir_dinamico=incluir_dinamico).a_dict()
