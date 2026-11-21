# -*- coding: ascii -*-
"""
Mapa de navegacion de una aplicacion con coordenadas y caminos verificados.

Une la capa logica del explorador (`UIStateMap`: estados, transiciones,
camino desde la raiz) con la capa fisica (elementos interactivos de cada estado
con su caja) en un JSON por equipo y aplicacion, y permite USARLO y
COMPROBARLO:

- `build_navigation_map(result, ...)` -> dict JSON: estados con profundidad y
  camino desde la raiz, elementos con caja normalizada al area cliente y caja
  absoluta observada, transiciones con la evidencia del clic real (punto,
  elemento bajo el puntero, estado antes y despues).
- `save_navigation_map` / `load_navigation_map`: `data/ui_maps/<machine_id>/
  <app_key>.json` (escritura atomica). Las coordenadas dependen del equipo,
  del monitor y de la escala: no van al catalogo global.
- `UINavigator`: llega a un estado reproduciendo su camino desde la raiz con
  clics en las coordenadas GUARDADAS (recalculadas sobre el area cliente
  actual de la ventana), verificando antes de cada clic el elemento bajo el
  puntero y despues el estado alcanzado. Un paso que no llega al estado
  esperado se informa como fallo, nunca como exito.
- `verify_all_paths`: para cada estado, reinicia a la raiz y reproduce el
  camino; devuelve el informe por estado. Es la prueba de que el mapa sirve.

Escribir texto solo se permite con ``allow_text=True`` (aplicaciones propias de
prueba): la exploracion nunca escribe en aplicaciones del usuario.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.core.log import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = 1
# Parecido minimo (Jaccard de elementos visibles) para aceptar que un estado
# observado es el esperado cuando su huella exacta difiere (contenido que
# cambia, como la hora o un contador).
ESTADO_SIMILITUD_MINIMA = 0.9

# Origen de las coordenadas de cada clic del navegador.
# "live": la caja ACTUAL del elemento en el arbol de accesibilidad (localizado
# por su referencia logica); si no se encuentra, la guardada. Sirve para
# ejecutar ordenes aunque el contenido se haya movido (un contacto nuevo arriba
# desplaza la lista).
# "stored": solo la caja guardada en el mapa. Es la prueba de que las
# coordenadas guardadas sirven (`verify_all_paths`).
COORDS_LIVE = "live"
COORDS_STORED = "stored"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_maps_dir() -> Path:
    from src.core.config import get_project_root

    return Path(get_project_root()) / "data" / "ui_maps"


def map_path(app_key: str, machine_id: str, base_dir: Optional[Path] = None) -> Path:
    clave = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(app_key).casefold()) or "app"
    equipo = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(machine_id)) or "equipo"
    return Path(base_dir or default_maps_dir()) / equipo / ("%s.json" % clave)


# ============================================================================
# CONSTRUCCION Y PERSISTENCIA
# ============================================================================


def build_navigation_map(
    result: Any,
    app_key: str,
    machine_id: str,
    window: Any = None,
    display: Any = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """JSON del mapa a partir de un `ExplorationResult` con capa fisica."""
    state_map = result.state_map
    physical = dict(getattr(result, "physical_states", {}) or {})
    states: Dict[str, Any] = {}
    for state_id, state in state_map.states.items():
        path = state_map.path_to(state_id)
        snapshot = physical.get(state_id) or {}
        states[state_id] = {
            "depth": int(state.depth),
            "path_from_root": (
                [
                    {
                        "from_state": t.from_state,
                        "action": t.action,
                        "element_key": str((t.evidence or {}).get("element_key", "")),
                        "element_ref": dict(t.element_ref),
                        "to_state": t.to_state,
                    }
                    for t in path
                ]
                if path is not None else None
            ),
            "reachable": path is not None,
            "visible_elements": list(state.visible_elements),
            "labels": list(snapshot.get("labels", []) or []),
            "window_client": snapshot.get("window_client"),
            "elements": list(snapshot.get("elements", []) or []),
        }
    transitions = [t.to_dict() for t in state_map.transitions]
    data: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "app_key": str(app_key),
        "machine_id": str(machine_id),
        "created_at": _ahora(),
        "root_state_id": state_map.root_state_id,
        "states": states,
        "transitions": transitions,
        "exploration": {
            "aborted": bool(result.aborted),
            "abort_reason": str(result.abort_reason or ""),
            "budget_exhausted": str(result.budget_exhausted or ""),
            "actions_performed": int(result.actions_performed),
            "elapsed_seconds": round(float(result.elapsed_seconds), 3),
            "resets": int(getattr(result, "resets", 0) or 0),
            "skipped_forbidden": list(result.skipped_forbidden),
            "no_effect": list(getattr(result, "no_effect", []) or []),
            "errors": list(result.errors),
        },
        "path_verification": None,
    }
    if window is not None:
        data["window"] = {
            "client_bounds": _rect_list(getattr(window, "client_bounds", None)),
            "is_maximized": bool(getattr(window, "is_maximized", False)),
            "scale_factor": getattr(window, "scale_factor", None),
            "dpi": getattr(window, "dpi", None),
        }
    if display is not None:
        data["display"] = {
            "display_id": getattr(display, "display_id", None),
            "scale_factor": getattr(display, "scale_factor", None),
            "bounds": _rect_list(getattr(display, "bounds", None)),
        }
    if extra:
        data.update(extra)
    return data


def _rect_list(rect: Any) -> Optional[List[float]]:
    if rect is None:
        return None
    try:
        return [float(rect.left), float(rect.top), float(rect.right), float(rect.bottom)]
    except AttributeError:
        return None


def save_navigation_map(data: Dict[str, Any], path: Optional[Path] = None, base_dir: Optional[Path] = None) -> Path:
    """Escribe el mapa de forma atomica (temporal + reemplazo)."""
    destino = Path(path) if path is not None else map_path(data["app_key"], data["machine_id"], base_dir)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ui_map_", suffix=".json", dir=str(destino.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)
        os.replace(tmp, destino)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return destino


def load_navigation_map(app_key: str, machine_id: str, base_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = map_path(app_key, machine_id, base_dir)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if int(data.get("schema", 0) or 0) != SCHEMA_VERSION:
        return None
    return data


def find_elements(data: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    """Elementos cuyo nombre o identificador contiene ``text`` (sin mayusculas,
    acentos ni puntuacion), con el estado donde estan y su profundidad."""
    from src.hands.calibration.ui_exploration import _normalize_text

    buscado = _normalize_text(text)
    encontrados: List[Dict[str, Any]] = []
    if not buscado:
        return encontrados
    for state_id, state in (data.get("states") or {}).items():
        for element in state.get("elements") or []:
            etiqueta = _normalize_text("%s %s" % (element.get("name", ""), element.get("identifier", "")))
            if buscado in etiqueta:
                encontrados.append({"state_id": state_id, "depth": state.get("depth"), "element": element})
    encontrados.sort(key=lambda e: (e["depth"] if e["depth"] is not None else 99))
    return encontrados


# ============================================================================
# NAVEGACION VERIFICADA
# ============================================================================


@dataclass
class StepEvidence:
    """Evidencia de un paso (clic) al recorrer un camino."""

    index: int
    element_key: str
    expected_from: str
    observed_from: str
    expected_to: str
    observed_to: str = ""
    click_point: Optional[List[float]] = None
    pointer_ok: bool = False
    element_under_pointer_ok: Optional[bool] = None
    reached: bool = False
    similarity: Optional[float] = None
    reason: str = ""
    # "live" (caja actual del elemento) o "stored" (caja guardada en el mapa).
    coordinate_source: str = ""
    # El punto del clic esta dentro de la caja ACTUAL del elemento buscado
    # (localizado en el arbol por su referencia logica). None: el elemento no
    # se localizo en el arbol actual y la identidad solo se comprueba despues
    # por el estado alcanzado.
    identity_ok: Optional[bool] = None
    # Distancia entre el centro guardado y el actual (px) cuando ambos existen.
    stored_offset_px: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class NavigationOutcome:
    """Resultado de ir a un estado o de actuar sobre un elemento."""

    ok: bool
    target_state: str
    steps: List[StepEvidence] = field(default_factory=list)
    reason: str = ""
    seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "target_state": self.target_state,
            "steps": [s.to_dict() for s in self.steps],
            "reason": self.reason,
            "seconds": round(self.seconds, 3),
        }


class UINavigator:
    """Usa un mapa guardado para llegar a estados y actuar, verificando cada paso.

    Argumentos:
        explorer: `DeepUIExplorer` configurado con el adaptador, la politica
            y la misma observacion que creo el mapa (la huella de estado debe
            calcularse igual). Su ``reset_root`` reinicia la app propia.
        data: mapa cargado (`build_navigation_map`/`load_navigation_map`).
        window_id, pid: ventana principal actual de la aplicacion.
        coordinates: ``COORDS_LIVE`` (por defecto) o ``COORDS_STORED``.
    """

    def __init__(
        self,
        explorer: Any,
        data: Dict[str, Any],
        window_id: int,
        pid: Optional[int],
        coordinates: str = COORDS_LIVE,
    ) -> None:
        if coordinates not in (COORDS_LIVE, COORDS_STORED):
            raise ValueError("coordinates debe ser 'live' o 'stored'")
        self.explorer = explorer
        self.data = data
        self.coordinates = coordinates
        explorer._main_window_id = int(window_id)
        explorer._pid = int(pid) if pid else None

    # ---------------------------------------------------------------- estado

    def observe(self) -> Any:
        return self.explorer._observe()

    def _state(self, state_id: str) -> Dict[str, Any]:
        state = (self.data.get("states") or {}).get(state_id)
        if state is None:
            raise KeyError("estado desconocido en el mapa: %s" % state_id)
        return state

    def matches_state(
        self, observed: Any, state_id: str, from_state_id: Optional[str] = None
    ) -> Tuple[bool, float]:
        """El estado observado es ``state_id``.

        Huella exacta, o bien (contenido que cambia, como mensajes nuevos o
        la hora) las etiquetas ``identificador|nombre`` que DISTINGUEN el
        estado esperado del anterior (``from_state_id``) estan presentes en
        al menos ESTADO_SIMILITUD_MINIMA. Asi "Chat con Lucia" no pasa por
        "Chat con Manolito" aunque la estructura sea identica.
        """
        if observed.state_id == state_id:
            return True, 1.0
        esperadas = set(self._state(state_id).get("labels") or [])
        if not esperadas:
            return False, 0.0
        if from_state_id and from_state_id in (self.data.get("states") or {}):
            anteriores = set(self._state(from_state_id).get("labels") or [])
            distintivas = esperadas - anteriores
            if distintivas:
                esperadas = distintivas
        vistas = self.explorer.state_labels(observed)
        parecido = float(len(esperadas & vistas)) / float(len(esperadas))
        return parecido >= ESTADO_SIMILITUD_MINIMA, parecido

    def reset_to_root(self) -> Any:
        """Reinicia la aplicacion propia y comprueba que esta en la raiz."""
        explorer = self.explorer
        if explorer.reset_root is None:
            raise RuntimeError("sin reset_root no se puede volver a la raiz de forma verificable")
        outcome = explorer.reset_root()
        if not outcome:
            raise RuntimeError("no se pudo reiniciar la aplicacion")
        window_id, pid = outcome
        explorer._main_window_id = int(window_id)
        explorer._pid = int(pid) if pid else None
        observed = self.observe()
        ok, _ = self.matches_state(observed, self.data["root_state_id"])
        if not ok:
            raise RuntimeError("tras reiniciar, la aplicacion no esta en el estado raiz del mapa")
        return observed

    # ---------------------------------------------------------------- clic

    def _client_rect(self) -> Optional[Tuple[float, float, float, float]]:
        window = self.explorer.adapter.get_window(int(self.explorer._main_window_id))
        if not window.ok or window.value is None:
            return None
        rect = window.value.client_bounds or window.value.frame_bounds or window.value.bounds
        if rect is None:
            return None
        return float(rect.left), float(rect.top), float(rect.right), float(rect.bottom)

    def _element(self, state_id: str, element_key: str) -> Dict[str, Any]:
        for element in self._state(state_id).get("elements") or []:
            if element.get("key") == element_key:
                return element
        raise KeyError("el elemento %s no esta en el estado %s del mapa" % (element_key, state_id))

    def _stored_box_now(self, element: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
        """Caja guardada (normalizada al area cliente) llevada a la ventana actual."""
        norm = element.get("box_client_norm")
        client = self._client_rect()
        if not norm or client is None:
            return None
        cl, ct, cr, cb = client
        width, height = cr - cl, cb - ct
        return (cl + norm[0] * width, ct + norm[1] * height, cl + norm[2] * width, ct + norm[3] * height)

    @staticmethod
    def _element_ref(element: Dict[str, Any]) -> Dict[str, Any]:
        """Referencia logica del elemento guardado (la misma que usa el explorador)."""
        return {
            "identifier": element.get("identifier") or "",
            "name": element.get("name") or "",
            "native_role": element.get("native_role") or "",
            "parent_name": element.get("parent_name") or "",
            "depth": element.get("tree_depth"),
        }

    def _live_box(self, element: Dict[str, Any], observed: Any) -> Optional[Tuple[float, float, float, float]]:
        """Caja actual del elemento en el arbol observado, o None si no se localiza
        de forma unica, no es visible o no tiene caja."""
        ref = self._element_ref(element)
        if ref.get("depth") is None:
            ref.pop("depth")
        node = self.explorer._locate(observed, ref)
        if node is None or not node.visible or node.offscreen:
            return None
        box = node.bbox
        if box is None or not box.is_valid():
            return None
        return float(box.left), float(box.top), float(box.right), float(box.bottom)

    def click_stored(
        self,
        state_id: str,
        element_key: str,
        step: Optional[StepEvidence] = None,
        observed: Any = None,
    ) -> StepEvidence:
        """Clic sobre un elemento del mapa, verificado antes de pulsar.

        Antes del clic: primer plano propio, el punto cae dentro de la caja
        ACTUAL del elemento si el arbol lo localiza (si no, la coordenada
        guardada ya no le corresponde y no se pulsa), y `PointerVerifier`
        comprueba posicion real, ventana y elemento bajo el puntero.
        ``observed``: observacion actual (evita leer el arbol otra vez).
        """
        from src.hands.calibration.coordinate_spaces import CoordinateSpace, SpaceBox, SpacePoint

        evidence = step or StepEvidence(0, element_key, state_id, "", "")
        element = self._element(state_id, element_key)
        explorer = self.explorer
        if not explorer._foreground_is_own():
            evidence.reason = "la ventana no esta en primer plano: no se hace clic"
            return evidence
        current = observed if observed is not None else explorer._observe_once()
        live = self._live_box(element, current)
        stored = self._stored_box_now(element)
        if self.coordinates == COORDS_LIVE and live is not None:
            box, evidence.coordinate_source = live, COORDS_LIVE
        elif stored is not None:
            box, evidence.coordinate_source = stored, COORDS_STORED
        else:
            evidence.reason = "el elemento no esta en la interfaz actual ni tiene caja guardada relativa a la ventana"
            return evidence
        x, y = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        evidence.click_point = [round(x, 1), round(y, 1)]
        if live is not None and stored is not None:
            dx = (live[0] + live[2]) / 2.0 - (stored[0] + stored[2]) / 2.0
            dy = (live[1] + live[3]) / 2.0 - (stored[1] + stored[3]) / 2.0
            evidence.stored_offset_px = round((dx * dx + dy * dy) ** 0.5, 1)
        if live is not None:
            evidence.identity_ok = bool(live[0] <= x < live[2] and live[1] <= y < live[3])
            if not evidence.identity_ok:
                evidence.reason = (
                    "las coordenadas guardadas ya no corresponden a %r (el elemento esta ahora en otra posicion): "
                    "no se hace clic" % (element.get("name") or element.get("identifier"))
                )
                return evidence
        space = CoordinateSpace.from_value(getattr(explorer.adapter, "desktop_space", "DESKTOP_PIXELS"))
        verification = explorer._verifier().move_and_verify(
            SpacePoint(x, y, space), int(explorer._main_window_id), expected_pid=explorer._pid,
            expected_box=SpaceBox(box[0], box[1], box[2], box[3], space),
        )
        evidence.pointer_ok = bool(getattr(verification, "ok", False))
        evidence.element_under_pointer_ok = getattr(verification, "element_ok", None)
        if not evidence.pointer_ok:
            evidence.reason = "coordenadas guardadas no verificadas: %s" % getattr(verification, "reason", "")
            return evidence
        clicked = explorer.adapter.click()
        if not clicked.ok:
            evidence.pointer_ok = False
            evidence.reason = "el clic fallo: %s" % clicked.error
        return evidence

    def go_to(self, state_id: str, from_root: bool = True) -> NavigationOutcome:
        """Llega a ``state_id`` por su camino desde la raiz, paso a paso."""
        started = time.monotonic()
        state = self._state(state_id)
        path = state.get("path_from_root")
        if path is None:
            return NavigationOutcome(False, state_id, reason="estado sin camino verificado desde la raiz")
        try:
            current = self.reset_to_root() if from_root else self.observe()
        except RuntimeError as exc:
            return NavigationOutcome(False, state_id, reason=str(exc), seconds=time.monotonic() - started)
        steps: List[StepEvidence] = []
        for index, edge in enumerate(path):
            step = StepEvidence(
                index=index, element_key=str(edge.get("element_key", "")),
                expected_from=str(edge["from_state"]), observed_from=current.state_id,
                expected_to=str(edge["to_state"]),
            )
            steps.append(step)
            if index == 0 and not from_root:
                # Con from_root la raiz ya se comprobo al reiniciar; en los
                # pasos siguientes el estado de partida es el que el paso
                # anterior acaba de verificar (por sus etiquetas distintivas).
                ok_from, _ = self.matches_state(current, step.expected_from)
                if not ok_from:
                    step.reason = "antes del clic la aplicacion no estaba en el estado esperado"
                    return NavigationOutcome(False, state_id, steps, step.reason, time.monotonic() - started)
            self.click_stored(step.expected_from, step.element_key, step, observed=current)
            if not step.pointer_ok:
                return NavigationOutcome(False, state_id, steps, step.reason, time.monotonic() - started)
            current = self.observe()
            step.observed_to = current.state_id
            step.reached, step.similarity = self.matches_state(current, step.expected_to, step.expected_from)
            if not step.reached:
                step.reason = "despues del clic la aplicacion no llego al estado esperado"
                return NavigationOutcome(False, state_id, steps, step.reason, time.monotonic() - started)
        return NavigationOutcome(True, state_id, steps, "", time.monotonic() - started)

    def type_into(self, state_id: str, element_key: str, text: str, allow_text: bool = False) -> StepEvidence:
        """Clic en un campo guardado y escritura. Solo aplicaciones propias de prueba."""
        if not allow_text:
            raise PermissionError("escribir texto requiere allow_text=True (nunca en apps del usuario)")
        step = self.click_stored(state_id, element_key)
        if not step.pointer_ok:
            return step
        typed = self.explorer.adapter.type_text(str(text))
        if not typed.ok:
            step.pointer_ok = False
            step.reason = "no se pudo escribir: %s" % typed.error
        return step


def verify_all_paths(navigator: UINavigator, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reproduce el camino de cada estado desde la raiz con las coordenadas
    GUARDADAS (prueba de que el mapa sirve) y anota el resultado en el mapa."""
    data = data if data is not None else navigator.data
    report: Dict[str, Any] = {
        "checked_at": _ahora(), "coordinates": COORDS_STORED, "states": {}, "ok": 0, "failed": 0,
    }
    previous = navigator.coordinates
    navigator.coordinates = COORDS_STORED
    try:
        for state_id, state in (data.get("states") or {}).items():
            if state_id == data.get("root_state_id"):
                continue
            outcome = navigator.go_to(state_id)
            report["states"][state_id] = outcome.to_dict()
            if outcome.ok:
                report["ok"] += 1
            else:
                report["failed"] += 1
    finally:
        navigator.coordinates = previous
    data["path_verification"] = report
    return report


__all__ = [
    "SCHEMA_VERSION",
    "COORDS_LIVE",
    "COORDS_STORED",
    "build_navigation_map",
    "save_navigation_map",
    "load_navigation_map",
    "map_path",
    "default_maps_dir",
    "find_elements",
    "StepEvidence",
    "NavigationOutcome",
    "UINavigator",
    "verify_all_paths",
]
