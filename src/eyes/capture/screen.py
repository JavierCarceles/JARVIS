# src/eyes/capture/screen.py
"""
Captura de pantalla y analisis para JARVIS con arquitectura de planificacion.

Este modulo proporciona:
- Captura de pantalla completa y regional.
- Analisis del estado del mundo.
- Deteccion de aplicaciones activas.
- Verificacion basica de elementos UI calibrados.
- Integracion con memoria de dominio.
- Comparacion de estado declarado (flags booleanas) con estado observable
  (ApplicationState de vision) para deteccion de discrepancias.

La geometria de monitores y ventanas pertenece a ScreenManager. Este modulo
no contiene offsets fijos, resoluciones prefijadas ni logica especifica de
Chrome o de otra aplicacion.

Las coordenadas de regiones y monitores se expresan en coordenadas absolutas
del escritorio virtual de Windows.
"""

from __future__ import annotations

import glob
import os
import shutil
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pyautogui
from PIL import ImageGrab

from src.memory.storage import MemoryType, get_memory_manager
from src.core.log import get_logger
from src.desktop.screen_manager import get_screen_manager

logger = get_logger(__name__)


class ApplicationState(Enum):
    """Estados conocidos de una aplicacion."""

    CLOSED = "closed"
    OPEN = "open"
    ACTIVE = "active"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"


@dataclass
class ApplicationInfo:
    """Informacion de una aplicacion detectada."""

    name: str
    state: ApplicationState
    window_title: Optional[str] = None
    window_class: Optional[str] = None
    monitor: int = 1
    position: Tuple[int, int] = (0, 0)
    size: Tuple[int, int] = (0, 0)
    visible_elements: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.visible_elements is None:
            self.visible_elements = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "window_title": self.window_title,
            "window_class": self.window_class,
            "monitor": self.monitor,
            "position": self.position,
            "size": self.size,
            "visible_elements": list(self.visible_elements or []),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ApplicationInfo":
        payload = dict(data or {})
        state_value = str(payload.get("state", ApplicationState.CLOSED.value)).lower()
        try:
            state = ApplicationState(state_value)
        except ValueError:
            state = ApplicationState.CLOSED

        position = payload.get("position", (0, 0))
        size = payload.get("size", (0, 0))

        try:
            position_tuple = tuple(position)[:2]
        except TypeError:
            position_tuple = (0, 0)
        try:
            size_tuple = tuple(size)[:2]
        except TypeError:
            size_tuple = (0, 0)

        if len(position_tuple) != 2:
            position_tuple = (0, 0)
        if len(size_tuple) != 2:
            size_tuple = (0, 0)

        return cls(
            name=str(payload.get("name", "unknown")),
            state=state,
            window_title=payload.get("window_title"),
            window_class=payload.get("window_class"),
            monitor=max(1, int(payload.get("monitor", 1) or 1)),
            position=(int(position_tuple[0]), int(position_tuple[1])),
            size=(int(size_tuple[0]), int(size_tuple[1])),
            visible_elements=list(payload.get("visible_elements", []) or []),
        )


# ============================================================================
# COMPARACION DE ESTADO DECLARADO vs. ESTADO OBSERVABLE
# ============================================================================

# Flags genericas de estado de ventana, separadas e independientes del dominio
# de la aplicacion. Representan el estado de la ventana con booleans y son el
# conjunto comun a toda aplicacion conocida en applications.json.
CANONICAL_WINDOW_FLAGS: Tuple[str, ...] = ("open", "active", "maximized", "focused")

# Conversion determinista de un estado observable (ApplicationState, producido
# por la capa Vision) a las flags genericas de estado de ventana {open, active,
# maximized, focused}.
#
# La derivacion obedece al contrato del Executor._update_world_state:
#   - app_open   -> open=True
#   - app_closed -> open=False
#   - app_active -> active=True
#   - app_minimized -> active=False (open permanece True, el proceso sigue activo)
# MINIMIZED y OPEN comparten las mismas flags genericas: el proceso corre y la
# ventana no es ni activa ni maximizada ni enfocada. La distincion visual entre
# ambas (ventana restaurada vs. minimizada) no afecta a las 4 flags canonicas.
APPLICATION_STATE_TO_WINDOW_FLAGS: Dict[ApplicationState, Dict[str, bool]] = {
    ApplicationState.CLOSED: {"open": False, "active": False, "maximized": False, "focused": False},
    ApplicationState.OPEN: {"open": True, "active": False, "maximized": False, "focused": False},
    ApplicationState.MINIMIZED: {"open": True, "active": False, "maximized": False, "focused": False},
    ApplicationState.ACTIVE: {"open": True, "active": True, "maximized": False, "focused": True},
    ApplicationState.MAXIMIZED: {"open": True, "active": True, "maximized": True, "focused": True},
}


def observable_state_to_flags(state: ApplicationState) -> Dict[str, bool]:
    """Convierte un :class:`ApplicationState` observable a las flags genericas
    booleanas de estado de ventana ``{open, active, maximized, focused}``.

    El estado observable proviene de la capa de vision (``Vision.detect_application_state``
    / :meth:`ScreenAnalyzer.analyze_application_state`) y representa una unica
    clasificacion visual. Esta funcion la descompone en las 4 flags canonicas
    que el modelo declarado (``applications.json`` / ``Executor.current_state``)
    utiliza para razonar sobre el mundo.

    **Contrato:**

    - Cada :class:`ApplicationState` mapea a exactamente una combinacion
      determinista de las 4 flags canonicas.
    - ``CLOSED`` -> todas ``False`` (la aplicacion no esta visible).
    - ``MINIMIZED`` -> ``open=True`` pero el resto ``False`` (el proceso corre
      y la ventana existe, aunque esta minimizada). Difiere visualmente de
      ``OPEN`` pero comparte las mismas flags canonicas.
    - ``ACTIVE`` -> ``open=True``, ``active=True``, ``focused=True`` (ventana de
      primer plano con foco de teclado).
    - ``MAXIMIZED`` -> ``open=True``, ``active=True``, ``maximized=True``,
      ``focused=True`` (ventana maximizada en primer plano).

    Args:
        state: Estado observable de la aplicacion (enum ``ApplicationState``).

    Returns:
        Diccionario inmutable con las 4 flags canonicas como booleans. Siempre
        contiene exactamente las claves ``open``, ``active``, ``maximized`` y
        ``focused``.

    Nota:
        Las flags de dominio (``playing``, ``streaming``, ``recording``) no se
        derivan de ``ApplicationState``; requieren deteccion visual especifica
        y no se incluyen en el resultado.
    """
    return dict(APPLICATION_STATE_TO_WINDOW_FLAGS[state])


def compare_declared_and_observable_state(
    declared: Dict[str, Any],
    observable_state: ApplicationState,
) -> Dict[str, Any]:
    """Compara el estado declarado (flags booleanas) con el estado observable
    (``ApplicationState``) para detectar discrepancias.

    El **estado declarado** es el modelo de creencias del sistema: proviene de
    ``applications.json`` (``states`` dict) o del estado en tiempo de ejecucion
    de :class:`Executor` (``current_state.application_states[app]``). Contiene
    al menos las 4 flags canonicas booleanas
    (``open``, ``active``, ``maximized``, ``focused``) y, opcionalmente, flags
    de dominio (``playing``, ``streaming``, ``recording``).

    El **estado observable** es lo que la capa de vision detecta visualmente en
    ese momento. Se convierte a flags canonicas mediante
    :func:`observable_state_to_flags`.

    **Contrato:**

    - Solo se comparan las 4 flags canonicas (``open``, ``active``,
      ``maximized``, ``focused``). Las flags de dominio no son comparables con
      ``ApplicationState`` y se ignoran en esta comparacion.
    - Si una flag canonica falta en el estado declarado, se asume ``False``
      (comportamiento consistente con el valor por defecto en
      ``applications.json``).
    - Cada flag se compara como booleano; valores no booleanos se convierten con
      ``bool()``.
    - Se reportan **todas** las discrepancias encontradas, no solo la primera.

    Args:
        declared: Diccionario de flags declaradas para la aplicacion. Normalmente
            ``applications[app]["states"]`` o ``current_state.application_states[app]``.
        observable_state: Estado observable detectado por vision.

    Returns:
        Diccionario con las claves:

        - ``match`` (``bool``): ``True`` si no hay discrepancias en ninguna
          flag canonica.
        - ``observable_state`` (``ApplicationState``): el estado observable
          recibido.
        - ``observable_flags`` (``Dict[str, bool]``): flags canonicas derivadas
          del estado observable.
        - ``declared_flags`` (``Dict[str, bool]``): las 4 flags canonicas
          leidas del estado declarado (faltantes -> ``False``).
        - ``discrepancies`` (``Dict[str, Dict[str, bool]]``): para cada flag
          discrepante, ``{flag: {"declared": bool, "observable": bool}}``.
          Vacio cuando ``match`` es ``True``.
    """
    observable_flags = observable_state_to_flags(observable_state)
    declared_flags: Dict[str, bool] = {}
    discrepancies: Dict[str, Dict[str, bool]] = {}

    for flag in CANONICAL_WINDOW_FLAGS:
        declared_value = bool(declared.get(flag, False))
        observable_value = observable_flags[flag]
        declared_flags[flag] = declared_value
        if declared_value != observable_value:
            discrepancies[flag] = {"declared": declared_value, "observable": observable_value}

    return {
        "match": len(discrepancies) == 0,
        "observable_state": observable_state,
        "observable_flags": observable_flags,
        "declared_flags": declared_flags,
        "discrepancies": discrepancies,
    }


def reconcile_observable_with_declared_state(
    declared: Dict[str, Any],
    observable_state: ApplicationState,
) -> Dict[str, Any]:
    """Resuelve una discrepancia entre el estado declarado y el observable.

    El **estado declarado** es el modelo de creencias del sistema: proviene de
    ``applications.json`` (``states`` dict) o del estado en tiempo de ejecucion
    de :class:`Executor` (``current_state.application_states[app]``). Contiene
    al menos las 4 flags canonicas booleanas.

    El **estado observable** es lo que la capa de vision detecta visualmente en
    ese momento (``Vision.detect_application_state`` /
    :meth:`ScreenAnalyzer.analyze_application_state``).

    **Comportamiento ante discrepancia** (hoja 3.4.3.3):

    La vision tiene prioridad sobre la configuracion estatica cuando detecta una
    aplicacion realmente presente. Por tanto:

    - Si ``match`` es ``True``, el estado declarado no necesita cambios.
    - Si ``match`` es ``False``, **las 4 flags canonicas del estado declarado se
      actualizan** para reflejar el estado observable real (las flags de dominio
      como ``playing``/``streaming``/``recording`` se conservan intactas, ya que
      no son comparables con ``ApplicationState``).
    - El estado declarado original recibido como argumento **no se muta**; el
      retorno incluye una copia reconciliada.

    Esto permite al :class:`Executor` actualizar su estado en tiempo real
    (``current_state.application_states[app]``) con la realidad observada y, de
    esa actualizacion, derivar una posible **replanificacion**. La configuracion
    estatica de ``applications.json`` no se escribe ni modifica.

    Args:
        declared: Diccionario de flags declaradas para la aplicacion. Normalmente
            ``applications[app]["states"]`` o ``current_state.application_states[app]``.
        observable_state: Estado observable detectado por vision
            (instancia de :class:`ApplicationState`).

    Returns:
        Diccionario con las claves:

        - ``match`` (``bool``): ``True`` si no habia discrepancias.
        - ``observable_state`` (``ApplicationState``): el estado observable
          recibido.
        - ``observable_flags`` (``Dict[str, bool]``): flags canonicas derivadas
          del estado observable.
        - ``declared_flags`` (``Dict[str, bool]``): las 4 flags canonicas
          leidas del estado declarado antes de la reconciliacion.
        - ``reconciled_flags`` (``Dict[str, Any]``): el estado declarado con las
          4 flags canonicas actualizadas a reflejar el observable; las flags de
          dominio y claves previamente ausentes se conservan.
        - ``discrepancies`` (``Dict[str, Dict[str, bool]]``): para cada flag
          discrepante, ``{flag: {"declared": bool, "observable": bool}}``.
        - ``reconciled`` (``bool``): ``True`` si se aplico una reconciliacion
          (es decir, ``match`` era ``False``); ``False`` si el estado declarado
          ya coincidia con el observable.
    """
    comparison = compare_declared_and_observable_state(declared, observable_state)

    observable_flags = comparison["observable_flags"]
    declared_flags = comparison["declared_flags"]
    discrepancies = comparison["discrepancies"]
    match = comparison["match"]

    # Se construye una copia del estado declarado para no mutar el original.
    reconciled_flags: Dict[str, Any] = dict(declared)

    if not match:
        # Prioridad a la vision: actualizar las 4 flags canonicas para reflejar
        # el estado observable real. Las flags de dominio se conservan.
        for flag in CANONICAL_WINDOW_FLAGS:
            reconciled_flags[flag] = observable_flags[flag]
        reconciled = True
    else:
        # Aunque no haya discrepancia, asegurar que las 4 flags canonicas esten
        # presentes en el resultado reconciliado (usando los valores observables,
        # que coinciden con los declarados en este caso).
        for flag in CANONICAL_WINDOW_FLAGS:
            reconciled_flags[flag] = observable_flags[flag]
        reconciled = False

    return {
        "match": match,
        "observable_state": observable_state,
        "observable_flags": observable_flags,
        "declared_flags": declared_flags,
        "reconciled_flags": reconciled_flags,
        "discrepancies": discrepancies,
        "reconciled": reconciled,
    }


@dataclass
class WorldState:
    """Estado del mundo usado por las APIs legacy de este modulo."""

    timestamp: float
    applications: Dict[str, ApplicationInfo]
    focused_application: Optional[str] = None
    active_monitor: int = 1
    available_monitors: Optional[List[int]] = None
    calibrated_elements: Optional[Dict[str, Dict[str, Any]]] = None
    known_urls: Optional[Dict[str, str]] = None
    system_resources: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.available_monitors is None:
            self.available_monitors = [1]
        if self.calibrated_elements is None:
            self.calibrated_elements = {}
        if self.known_urls is None:
            self.known_urls = {}
        if self.system_resources is None:
            self.system_resources = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "applications": {
                key: value.to_dict() if hasattr(value, "to_dict") else value
                for key, value in self.applications.items()
            },
            "focused_application": self.focused_application,
            "active_monitor": self.active_monitor,
            "available_monitors": list(self.available_monitors or []),
            "calibrated_elements": dict(self.calibrated_elements or {}),
            "known_urls": dict(self.known_urls or {}),
            "system_resources": dict(self.system_resources or {}),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "WorldState":
        payload = dict(data or {})
        applications: Dict[str, ApplicationInfo] = {}
        for app_name, app_data in (payload.get("applications", {}) or {}).items():
            if isinstance(app_data, dict):
                app_data = dict(app_data)
                app_data.setdefault("name", app_name)
                applications[str(app_name)] = ApplicationInfo.from_dict(app_data)
            else:
                applications[str(app_name)] = ApplicationInfo(
                    name=str(app_name),
                    state=ApplicationState.CLOSED,
                )

        try:
            active_monitor = max(1, int(payload.get("active_monitor", 1) or 1))
        except (TypeError, ValueError):
            active_monitor = 1

        return cls(
            timestamp=float(payload.get("timestamp", time.time())),
            applications=applications,
            focused_application=payload.get("focused_application"),
            active_monitor=active_monitor,
            available_monitors=[
                int(value)
                for value in (payload.get("available_monitors", [1]) or [1])
                if str(value).isdigit()
            ] or [1],
            calibrated_elements=dict(payload.get("calibrated_elements", {}) or {}),
            known_urls=dict(payload.get("known_urls", {}) or {}),
            system_resources=dict(payload.get("system_resources", {}) or {}),
        )


pyautogui.PAUSE = 0.05


# ============================================================================
# UTILIDADES DE MONITORES
# ============================================================================


def _get_available_monitor_numbers() -> List[int]:
    """Obtiene todos los monitores reales detectados por ScreenManager."""

    try:
        screen_manager = get_screen_manager()
        refresh = getattr(screen_manager, "refresh_monitors", None)
        if callable(refresh):
            refresh()

        monitors = list(getattr(screen_manager, "monitors", []) or [])
        numbers: List[int] = []
        for position, monitor in enumerate(monitors, start=1):
            number = getattr(monitor, "monitor_id", None)
            if not isinstance(number, int) or number < 1:
                candidate_index = getattr(monitor, "index", None)
                if isinstance(candidate_index, int):
                    # ScreenManager usa index 0-based.
                    number = candidate_index + 1
            if not isinstance(number, int) or number < 1:
                number = position
            if number not in numbers:
                numbers.append(number)

        return numbers or [1]
    except Exception as exc:
        logger.debug("_get_available_monitor_numbers: %s", exc)

        return [1]


def _get_monitor_number(monitor: Any) -> Optional[int]:
    """Obtiene el identificador logico de un MonitorInfo sin asumir un campo unico."""

    if monitor is None:
        return None

    for attribute in ("monitor_id", "screen_number", "number"):
        value = getattr(monitor, attribute, None)
        if isinstance(value, int) and value > 0:
            return value

    index = getattr(monitor, "index", None)
    if isinstance(index, int) and index >= 0:
        return index + 1

    return None


# ============================================================================
# ANALISIS DE PANTALLAS Y ESTADO
# ============================================================================


class ScreenAnalyzer:
    """Analizador de pantallas integrado con la capa Vision."""

    def __init__(self) -> None:
        self.memory_manager = get_memory_manager()
        self._vision = None

    def _get_vision(self):
        """Inicializa Vision de forma diferida para evitar importaciones circulares."""

        if self._vision is not None:
            return self._vision

        try:
            from src.eyes.vision.vision import Vision

            self._vision = Vision()
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_vision: %s", exc)


        return self._vision

    def analyze_application_state(self, app_name: str) -> ApplicationInfo:
        """Analiza una aplicacion en todos los monitores disponibles."""

        target = str(app_name or "").strip()
        if not target:
            return ApplicationInfo(name=target, state=ApplicationState.CLOSED)

        vision = self._get_vision()
        if vision is not None:
            try:
                result = vision.detect_application_state(target)
                if isinstance(result, ApplicationInfo):
                    return result
                if hasattr(result, "to_dict"):
                    return ApplicationInfo.from_dict(result.to_dict())
                if isinstance(result, dict):
                    result = dict(result)
                    result.setdefault("name", target)
                    return ApplicationInfo.from_dict(result)
            except Exception as exc:
                logger.debug("ScreenAnalyzer.analyze_application_state: %s", exc)


        return self._fallback_detect_application_state(target)

    def _fallback_detect_application_state(self, app_name: str) -> ApplicationInfo:
        """Fallback no visual usando la ventana foreground cuando sea posible."""

        try:
            import pygetwindow as gw

            active_window = gw.getActiveWindow()
            if active_window is not None:
                title = str(getattr(active_window, "title", "") or "")
                if app_name.lower() in title.lower():
                    monitor = get_screen_manager().get_monitor_for_window(active_window)
                    monitor_number = _get_monitor_number(monitor) or 1
                    return ApplicationInfo(
                        name=app_name,
                        state=ApplicationState.ACTIVE,
                        window_title=title or None,
                        monitor=monitor_number,
                        position=(
                            int(getattr(active_window, "left", 0)),
                            int(getattr(active_window, "top", 0)),
                        ),
                        size=(
                            max(0, int(getattr(active_window, "width", 0))),
                            max(0, int(getattr(active_window, "height", 0))),
                        ),
                    )
        except Exception as exc:
            logger.debug("ScreenAnalyzer._fallback_detect_application_state: %s", exc)


        return ApplicationInfo(name=app_name, state=ApplicationState.CLOSED)

    def build_world_state(self) -> WorldState:
        """Construye el estado del mundo usando la capa Vision cuando esta disponible."""

        logger.info(r"Construyendo estado del mundo...")

        start_time = time.time()
        monitor_numbers = _get_available_monitor_numbers()

        vision = self._get_vision()
        if vision is not None:
            try:
                visual_state = vision.analyze_screen_for_world_state()
                world_state = self._convert_visual_world_state(
                    visual_state,
                    monitor_numbers,
                    start_time,
                )
                self.memory_manager.save_world_state(world_state.to_dict())
                return world_state
            except Exception as exc:
                logger.debug("ScreenAnalyzer.build_world_state: %s", exc)


        # Fallback: informacion minima sin asumir un numero fijo de monitores.
        applications: Dict[str, ApplicationInfo] = {}
        for app_name in self._get_known_applications():
            applications[app_name] = self._fallback_detect_application_state(app_name)

        world_state = WorldState(
            timestamp=start_time,
            applications=applications,
            focused_application=self._detect_focused_application(applications),
            active_monitor=self._get_active_monitor(),
            available_monitors=monitor_numbers,
            calibrated_elements=self._get_calibrated_elements(),
            known_urls=self._get_known_urls(),
            system_resources=self._get_system_resources(),
        )

        try:
            self.memory_manager.save_world_state(world_state.to_dict())
        except Exception as exc:
            logger.debug("ScreenAnalyzer.build_world_state: %s", exc)


        logger.info(r"[SCREEN-ANALYZER] Estado construido en %.2fs", time.time() - start_time)

        return world_state

    def _convert_visual_world_state(
        self,
        visual_state: Any,
        monitor_numbers: List[int],
        timestamp: float,
    ) -> WorldState:
        """Adapta el WorldState de memoria de Vision a la API legacy de este modulo."""

        applications: Dict[str, ApplicationInfo] = {}
        visual_apps = getattr(visual_state, "applications", {}) or {}

        state_map = {
            "closed": ApplicationState.CLOSED,
            "open": ApplicationState.OPEN,
            "active": ApplicationState.ACTIVE,
            "minimized": ApplicationState.MINIMIZED,
            "maximized": ApplicationState.MAXIMIZED,
        }

        if isinstance(visual_apps, dict):
            for key, raw in visual_apps.items():
                if isinstance(raw, ApplicationInfo):
                    applications[str(key)] = raw
                    continue
                if not isinstance(raw, dict):
                    applications[str(key)] = ApplicationInfo(
                        name=str(key),
                        state=ApplicationState.CLOSED,
                    )
                    continue

                state_value = str(raw.get("state", "closed") or "closed").lower()

                # Un estado desconocido NO se convierte en un estado valido por
                # defecto. Anteriormente state_map.get(...) caia en
                # ApplicationState.OPEN, lo cual podia llevar a creencias falsas
                # sobre una aplicacion abierta. Usamos CLOSED como fallback seguro
                # y registramos el estado desconocido.
                if state_value in state_map:
                    resolved_state = state_map[state_value]
                else:
                    resolved_state = ApplicationState.CLOSED
                    logger.info(f"Estado desconocido omitido en screen.py: '{state_value}' "
                        "")

                applications[str(key)] = ApplicationInfo(
                    name=str(raw.get("name", key)),
                    state=resolved_state,
                    window_title=raw.get("window_title"),
                    window_class=raw.get("window_class"),
                    monitor=max(1, int(raw.get("monitor", 1) or 1)),
                    position=tuple(raw.get("position", (0, 0)))[:2]
                    if isinstance(raw.get("position"), (list, tuple))
                    and len(raw.get("position")) >= 2
                    else (0, 0),
                    size=tuple(raw.get("size", (0, 0)))[:2]
                    if isinstance(raw.get("size"), (list, tuple))
                    and len(raw.get("size")) >= 2
                    else (0, 0),
                    visible_elements=list(raw.get("visible_elements", []) or []),
                )

        system_info = getattr(visual_state, "system_info", {}) or {}
        if not isinstance(system_info, dict):
            system_info = {}

        focused_application = system_info.get("focused_application")
        active_monitor_value = system_info.get("active_monitor")
        try:
            active_monitor = int(active_monitor_value)
        except (TypeError, ValueError):
            active_monitor = self._get_active_monitor()
        if active_monitor not in monitor_numbers:
            active_monitor = monitor_numbers[0] if monitor_numbers else 1

        calibrated_elements = system_info.get("calibrated_elements", {}) or {}
        known_urls = system_info.get("known_urls", {}) or {}

        world_state = WorldState(
            timestamp=timestamp,
            applications=applications,
            focused_application=str(focused_application) if focused_application else None,
            active_monitor=active_monitor,
            available_monitors=monitor_numbers,
            calibrated_elements=dict(calibrated_elements),
            known_urls=dict(known_urls),
            system_resources={
                "visible_text": system_info.get("visible_text", ""),
            },
        )
        return world_state

    def _get_known_applications(self) -> List[str]:
        """Obtiene aplicaciones conocidas desde memoria y descubrimiento global."""

        names: List[str] = []

        try:
            entities = self.memory_manager.get_entities_by_type("application") or []
            names.extend(
                str(entity.name)
                for entity in entities
                if getattr(entity, "name", None)
            )
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_known_applications: %s", exc)


        try:
            entities = self.memory_manager.get_entities_by_type("platform") or []
            names.extend(
                str(entity.name)
                for entity in entities
                if getattr(entity, "name", None)
            )
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_known_applications: %s", exc)


        try:
            from src.hands.calibration.calibration_manager import get_calibration_manager

            manager = get_calibration_manager()
            discover = getattr(manager, "discover_applications", None)
            if callable(discover):
                discovered = discover() or []
                for app in discovered:
                    if isinstance(app, str):
                        names.append(app)
                    else:
                        name = getattr(app, "name", None)
                        if name:
                            names.append(str(name))
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_known_applications: %s", exc)


        # Fallback minimo para instalaciones donde la memoria todavia este vacia.
        names.extend(["chrome", "edge", "firefox", "notepad", "calculator", "paint", "explorer", "cmd", "spotify"])

        unique: List[str] = []
        seen = set()
        for name in names:
            normalized = str(name).strip()
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                unique.append(normalized)
        return unique

    def _detect_focused_application(
        self,
        applications: Dict[str, ApplicationInfo],
    ) -> Optional[str]:
        """Detecta la aplicacion enfocada mediante la ventana foreground."""

        try:
            import pygetwindow as gw

            active_window = gw.getActiveWindow()
            if active_window is None:
                return None

            window_title = str(getattr(active_window, "title", "") or "").lower()
            if not window_title:
                return None

            for app_name, app_info in applications.items():
                if app_info.window_title and app_info.window_title.lower() in window_title:
                    return app_name

            for app_name in applications:
                if str(app_name).lower() in window_title:
                    return app_name

            for app_name, app_info in applications.items():
                if app_info.state == ApplicationState.ACTIVE:
                    return app_name
        except Exception as exc:
            logger.debug("ScreenAnalyzer._detect_focused_application: %s", exc)


        return None

    def _get_active_monitor(self) -> int:
        """Obtiene el monitor de la ventana foreground desde ScreenManager."""

        try:
            screen_manager = get_screen_manager()
            foreground_getter = getattr(screen_manager, "get_foreground_window", None)
            if callable(foreground_getter):
                active_window = foreground_getter()
            else:
                import pygetwindow as gw
                active_window = gw.getActiveWindow()

            if active_window is not None:
                monitor = screen_manager.get_monitor_for_window(active_window)
                number = _get_monitor_number(monitor)
                if number is not None:
                    return number

            active_getter = getattr(screen_manager, "get_active_monitor", None)
            if callable(active_getter):
                monitor = active_getter()
                number = _get_monitor_number(monitor)
                if number is not None:
                    return number

            primary = screen_manager.get_primary_monitor()
            number = _get_monitor_number(primary)
            if number is not None:
                return number
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_active_monitor: %s", exc)


        return _get_available_monitor_numbers()[0]

    def _get_calibrated_elements(self) -> Dict[str, Dict[str, Any]]:
        """Obtiene elementos calibrados desde memoria."""

        try:
            state = self.memory_manager.storage.load(MemoryType.STATE)
            if isinstance(state, dict):
                return dict(state.get("calibrated_elements", {}) or {})
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_calibrated_elements: %s", exc)

        return {}

    def _get_known_urls(self) -> Dict[str, str]:
        """Obtiene URLs conocidas desde memoria de dominio."""

        try:
            streamers = self.memory_manager.get_entities_by_type("streamer") or []
            platforms = self.memory_manager.get_entities_by_type("platform") or []
            urls: Dict[str, str] = {}
            for entity in list(streamers) + list(platforms):
                properties = getattr(entity, "properties", {}) or {}
                url = properties.get("url")
                if url:
                    urls[str(entity.name)] = str(url)
            return urls
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_known_urls: %s", exc)

            return {}

    def _get_system_resources(self) -> Dict[str, Any]:
        """Obtiene recursos basicos del sistema."""

        try:
            import psutil

            if os.name == "nt":
                disk_root = f"{os.environ.get('SystemDrive', 'C:')}\\"
            else:
                disk_root = "/"

            battery = None
            sensors_battery = getattr(psutil, "sensors_battery", None)
            if callable(sensors_battery):
                try:
                    battery_info = sensors_battery()
                    if battery_info is not None:
                        battery = {
                            "percent": getattr(battery_info, "percent", None),
                            "plugged": getattr(battery_info, "power_plugged", None),
                        }
                except Exception:
                    battery = None

            return {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(disk_root).percent,
                "battery": battery,
            }
        except Exception as exc:
            logger.debug("ScreenAnalyzer._get_system_resources: %s", exc)

            return {}


# ============================================================================
# SISTEMA DE CAPTURA
# ============================================================================


class ScreenCapture:
    """Sistema de captura con geometria delegada a ScreenManager."""

    def __init__(self) -> None:
        self.analyzer: Optional[ScreenAnalyzer] = None
        logger.debug(r"Sistema de captura inicializado")


    def _get_analyzer(self) -> Optional[ScreenAnalyzer]:
        if self.analyzer is None:
            try:
                self.analyzer = ScreenAnalyzer()
            except Exception as exc:
                logger.debug("ScreenCapture._get_analyzer: %s", exc)

        return self.analyzer

    # ========================================================================
    # MONITOR
    # ========================================================================

    def capture_monitor(
        self,
        monitor_num: int,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura exactamente el monitor indicado mediante ScreenManager."""

        try:
            screen_manager = get_screen_manager()
            result = screen_manager.capture_monitor(int(monitor_num))
            if not result:
                return None

            source_path = Path(str(result))
            if not source_path.exists():

                return None

            if save_path is None:
                return str(source_path.resolve())

            output_path = Path(save_path)
            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, output_path)
            return str(output_path.resolve())
        except Exception as exc:
            logger.debug("ScreenCapture.capture_monitor: %s", exc)

            return None

    # ========================================================================
    # REGION
    # ========================================================================

    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura una region expresada en coordenadas absolutas del escritorio."""

        try:
            x = int(x)
            y = int(y)
            width = int(width)
            height = int(height)
            if width <= 0 or height <= 0:
                return None

            bbox = (x, y, x + width, y + height)
            try:
                screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
            except TypeError:
                screenshot = ImageGrab.grab(bbox=bbox)

            output_path = self._prepare_output_path(save_path, "region")
            screenshot.save(str(output_path))
            return str(output_path.resolve())
        except Exception as exc:
            logger.debug("ScreenCapture.capture_region: %s", exc)

            return None

    # ========================================================================
    # ELEMENTO
    # ========================================================================

    def capture_element(
        self,
        element_coords: Dict[str, Any],
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura una region descrita por x/y/width/height."""

        if not isinstance(element_coords, dict):
            return None

        try:
            return self.capture_region(
                x=int(element_coords.get("x", 0)),
                y=int(element_coords.get("y", 0)),
                width=int(element_coords.get("width", 0)),
                height=int(element_coords.get("height", 0)),
                save_path=save_path,
            )
        except (TypeError, ValueError):
            return None

    # ========================================================================
    # VENTANA ACTIVA
    # ========================================================================

    def capture_active_window(
        self,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura la ventana foreground actual."""

        try:
            import pygetwindow as gw

            active_window = gw.getActiveWindow()
            if active_window is None:
                return None

            left = int(getattr(active_window, "left", 0))
            top = int(getattr(active_window, "top", 0))
            width = int(getattr(active_window, "width", 0))
            height = int(getattr(active_window, "height", 0))
            if width <= 0 or height <= 0:
                return None

            bbox = (left, top, left + width, top + height)
            try:
                screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
            except TypeError:
                screenshot = ImageGrab.grab(bbox=bbox)

            output_path = self._prepare_output_path(save_path, "window")
            screenshot.save(str(output_path))
            return str(output_path.resolve())
        except Exception as exc:
            logger.debug("ScreenCapture.capture_active_window: %s", exc)

            return None

    def _prepare_output_path(
        self,
        save_path: Optional[str],
        prefix: str,
    ) -> Path:
        """Prepara la ruta de salida para una captura."""

        if save_path:
            output_path = Path(save_path)
        else:
            timestamp = int(time.time() * 1000)
            output_path = Path.cwd() / f"temp_{prefix}_{timestamp}.png"

        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    # ========================================================================
    # ESCRITORIO COMPLETO
    # ========================================================================

    def capture_desktop(
        self,
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """Captura el rectangulo completo del escritorio virtual."""

        try:
            screen_manager = get_screen_manager()
            refresh = getattr(screen_manager, "refresh_monitors", None)
            if callable(refresh):
                refresh()

            monitors = list(getattr(screen_manager, "monitors", []) or [])
            if not monitors:
                return None

            left = min(int(m.left) for m in monitors)
            top = min(int(m.top) for m in monitors)
            right = max(int(m.right) for m in monitors)
            bottom = max(int(m.bottom) for m in monitors)

            try:
                screenshot = ImageGrab.grab(
                    bbox=(left, top, right, bottom),
                    all_screens=True,
                )
            except TypeError:
                screenshot = ImageGrab.grab(
                    bbox=(left, top, right, bottom),
                )

            output_path = self._prepare_output_path(save_path, "desktop")
            screenshot.save(str(output_path))
            return str(output_path.resolve())
        except Exception as exc:
            logger.debug("ScreenCapture.capture_desktop: %s", exc)

            return None

    # ========================================================================
    # ESTADO DEL MUNDO
    # ========================================================================

    def get_world_state(self) -> WorldState:
        analyzer = self._get_analyzer()
        if analyzer is None:
            return WorldState(applications={}, timestamp=time.time())
        return analyzer.build_world_state()

    def get_application_state(self, app_name: str) -> ApplicationInfo:
        analyzer = self._get_analyzer()
        if analyzer is None:
            return ApplicationInfo(name=app_name, state=ApplicationState.CLOSED)
        return analyzer.analyze_application_state(app_name)

    def check_element_visibility(self, element_name: str) -> bool:
        """Comprueba visibilidad a partir del estado visual disponible."""

        target = str(element_name or "").strip().lower()
        if not target:
            return False

        try:
            world_state = self.get_world_state()
            if world_state.focused_application:
                info = world_state.applications.get(world_state.focused_application)
                if info and any(
                    target == str(element).strip().lower()
                    for element in (info.visible_elements or [])
                ):
                    return True

            for info in world_state.applications.values():
                if any(
                    target == str(element).strip().lower()
                    for element in (info.visible_elements or [])
                ):
                    return True
            return False
        except Exception as exc:
            logger.debug("ScreenCapture.check_element_visibility: %s", exc)

            return False

    # ========================================================================
    # LIMPIEZA
    # ========================================================================

    def clean_temp_files(self, pattern: str = "temp_*.png") -> None:
        """Elimina capturas temporales del directorio actual."""

        try:
            for file_path in glob.glob(pattern):
                try:
                    Path(file_path).unlink()

                except Exception as exc:
                    logger.debug("ScreenCapture.clean_temp_files: %s", exc)

        except Exception as exc:
            logger.debug("ScreenCapture.clean_temp_files: %s", exc)



# ============================================================================
# FUNCIONES DE COMPATIBILIDAD
# ============================================================================


def capture_screen(filepath: str = "screenshot.png") -> str:
    """Captura el escritorio virtual completo."""

    screen_capture = get_screen_capture()
    return screen_capture.capture_desktop(filepath) or ""


def capture_captcha_area(
    pantalla: str,
    region_captcha: Tuple[int, int, int, int],
    img_captcha_path: str,
) -> bool:
    """Captura una region del escritorio para compatibilidad legacy."""

    del pantalla  # Parametro legacy; no se usa para calcular coordenadas.
    screen_capture = get_screen_capture()
    x, y, width, height = region_captcha
    result = screen_capture.capture_region(
        x,
        y,
        width,
        height,
        img_captcha_path,
    )
    return result is not None


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================


_screen_capture_instance: Optional[ScreenCapture] = None


def get_screen_capture() -> ScreenCapture:
    """Obtiene la instancia global de captura."""

    global _screen_capture_instance
    if _screen_capture_instance is None:
        _screen_capture_instance = ScreenCapture()
    return _screen_capture_instance


__all__ = [
    "ApplicationState",
    "ApplicationInfo",
    "WorldState",
    "ScreenAnalyzer",
    "ScreenCapture",
    "capture_screen",
    "capture_captcha_area",
    "get_screen_capture",
    "CANONICAL_WINDOW_FLAGS",
    "APPLICATION_STATE_TO_WINDOW_FLAGS",
    "observable_state_to_flags",
    "compare_declared_and_observable_state",
    "reconcile_observable_with_declared_state",
]
