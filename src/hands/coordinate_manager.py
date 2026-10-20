"""
Gestor unificado de coordenadas para JARVIS - FASE 13.

Responsabilidades:
- Administrar recursos UI calibrados.
- Proporcionar capacidades de UI al planificador.
- Gestionar estado de calibración.
- Convertir y validar sistemas de coordenadas.
- Leer datos existentes de ``macros_coords.json``.
- Mantener compatibilidad con APIs legacy.

Principios:
- Las coordenadas proceden de calibración/detección real; no se fabrican.
- ``sN`` identifica el monitor N, no una esquina ni un offset.
- La calibración universal no depende de Chrome ni de otra aplicación concreta.
- La detección/movimiento de ventanas corresponde a ScreenManager /
  CalibrationManager; aquí solo se exponen utilidades de coordenadas y recursos.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pygetwindow as gw

from src.utils.logger import get_logger
from src.utils.screen_manager import get_monitor_info, get_screen_manager

logger = get_logger(__name__)


class ResourceType(Enum):
    """Tipos de recursos UI gestionados por el coordinate manager."""

    ELEMENT = "element"
    REGION = "region"
    APPLICATION = "application"
    WINDOW = "window"
    MONITOR = "monitor"


class CalibrationStrategy(Enum):
    """Estrategias de calibración disponibles."""

    VISUAL_DETECTION = "visual_detection"
    WINDOW_DETECTION = "window_detection"
    SCREEN_CAPTURE = "screen_capture"
    KEYBOARD_SHORTCUT = "keyboard_shortcut"
    HOTKEY = "hotkey"


@dataclass
class UIResource:
    """Recurso UI calibrado utilizable por acciones del planificador."""

    id: str
    name: str
    resource_type: ResourceType
    application: str
    element_type: str
    calibration_strategy: CalibrationStrategy
    calibrated_coordinates: Dict[int, Tuple[int, int]]
    calibrated_regions: Dict[int, Tuple[int, int, int, int]]
    confidence: float
    is_available: bool
    is_calibrated: bool
    last_calibration_time: Optional[float] = None
    alternatives: List[str] = field(default_factory=list)
    fallback_strategies: List[str] = field(default_factory=list)
    description: str = ""
    requirements: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.requirements = list(self.requirements or [])
        self.alternatives = list(self.alternatives or [])
        self.fallback_strategies = list(self.fallback_strategies or [])
        self.calibrated_coordinates = dict(self.calibrated_coordinates or {})
        self.calibrated_regions = dict(self.calibrated_regions or {})
        self.metadata = dict(self.metadata or {})
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.calibrated_coordinates or self.calibrated_regions:
            self.is_calibrated = True
            self.is_available = True

    @property
    def is_usable(self) -> bool:
        return bool(self.is_available and self.is_calibrated)

    def get_coordinates_for_screen(
        self, screen_number: int
    ) -> Optional[Tuple[int, int]]:
        try:
            return self.calibrated_coordinates.get(int(screen_number))
        except (TypeError, ValueError):
            return None

    def get_region_for_screen(
        self,
        screen_number: int,
    ) -> Optional[Tuple[int, int, int, int]]:
        try:
            return self.calibrated_regions.get(int(screen_number))
        except (TypeError, ValueError):
            return None

    def get_best_coordinates(self) -> Optional[Tuple[int, int]]:
        """Devuelve coordenadas del monitor activo o, en su defecto, de cualquier monitor calibrado."""
        screen_manager = get_screen_manager()

        try:
            active_monitor = screen_manager.get_active_monitor()
            active_number = CoordinateManager.monitor_number_from_object(active_monitor)
            if active_number is not None:
                coords = self.get_coordinates_for_screen(active_number)
                if coords is not None:
                    return coords
        except Exception as exc:
            logger._print_log("debug", r"[COORDINATE-MANAGER] No se pudo determinar el monitor activo: %s [file:coordinate_manager.py, method:get_active_screen_coordinates, line:124]", "coordinate_manager.py", "method", 124)

        for screen_number in sorted(self.calibrated_coordinates):
            coords = self.get_coordinates_for_screen(screen_number)
            if coords is not None:
                return coords

        return None

    def get_alternatives(self) -> List["UIResource"]:
        manager = get_coordinate_manager()
        return [
            resource
            for resource_id in self.alternatives
            for resource in [manager.get_ui_resource(resource_id)]
            if resource is not None and resource.is_usable
        ]

    def can_use_fallback_strategy(self, strategy_name: str) -> bool:
        return str(strategy_name or "").strip().lower() in {
            str(item).strip().lower() for item in self.fallback_strategies
        }


class UICapability:
    """Capacidad UI que puede ser utilizada por una acción."""

    def __init__(self, name: str, description: str, required_resources: List[str]):
        self.name = name
        self.description = description
        self.required_resources = list(required_resources or [])
        self.preconditions: List[str] = []
        self.effects: List[str] = []
        self.alternative_strategies: List[str] = []

    def can_execute_with_resources(self, available_resources: Set[str]) -> bool:
        return all(
            resource_id in available_resources
            for resource_id in self.required_resources
        )


class CoordinateSystem(Enum):
    """Sistemas de coordenadas soportados por JARVIS."""

    RELATIVE_SCREEN = "relative_screen"
    ABSOLUTE_DESKTOP = "absolute_desktop"
    WINDOW_RELATIVE = "window_relative"


@dataclass
class BoundingBox:
    """Rectángulo delimitador de un elemento."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    @property
    def center(self) -> Tuple[int, int]:
        return self.center_x, self.center_y

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y,
        }


@dataclass
class ElementInfo:
    """Información de un elemento calibrado (compatibilidad)."""

    name: str
    element_type: str
    bounding_box: BoundingBox
    confidence: float
    coordinate_system: CoordinateSystem
    screen_number: int
    window_rect: Optional[BoundingBox] = None
    description: str = ""

    def get_absolute_coordinates(self) -> Tuple[int, int]:
        if self.coordinate_system == CoordinateSystem.ABSOLUTE_DESKTOP:
            return self.bounding_box.center

        if self.coordinate_system == CoordinateSystem.RELATIVE_SCREEN:
            monitor = get_monitor_info(self.screen_number)
            if monitor is None:
                logger._print_log("error", r"[COORDINATE-MANAGER] Monitor %s no encontrado [file:coordinate_manager.py, method:get_absolute_coordinates, line:234]", "coordinate_manager.py", "method", 234)
                return self.bounding_box.center
            return (
                int(monitor.left) + self.bounding_box.center_x,
                int(monitor.top) + self.bounding_box.center_y,
            )

        if self.coordinate_system == CoordinateSystem.WINDOW_RELATIVE:
            if self.window_rect is None:
                logger._print_log("error", r"[COORDINATE-MANAGER] WINDOW_RELATIVE requiere window_rect [file:coordinate_manager.py, method:get_absolute_coordinates, line:243]", "coordinate_manager.py", "method", 243)
                return self.bounding_box.center
            return (
                self.window_rect.x + self.bounding_box.center_x,
                self.window_rect.y + self.bounding_box.center_y,
            )

        logger._print_log("error", r"[COORDINATE-MANAGER] Sistema no soportado: %s [file:coordinate_manager.py, method:get_absolute_coordinates, line:252]", "coordinate_manager.py", "method", 250)
        return self.bounding_box.center


class CoordinateManager:
    """Gestor centralizado de conocimiento UI y coordenadas calibradas."""

    def __init__(self) -> None:
        self.screen_manager = get_screen_manager()
        self.ui_resources: Dict[str, UIResource] = {}
        self.ui_capabilities: Dict[str, UICapability] = {}
        self.ui_knowledge: Dict[str, Any] = {}
        self.calibration_policies: Dict[str, Any] = {}

        logger._print_log("info", r"[COORDINATE-MANAGER] Gestor FASE 13 inicializado [file:coordinate_manager.py, method:__init__, line:275]", "coordinate_manager.py", "method", 264)
        self._initialize_base_capabilities()
        self._load_ui_knowledge()

    # ------------------------------------------------------------------
    # CAPACIDADES
    # ------------------------------------------------------------------

    def _initialize_base_capabilities(self) -> None:
        focus = UICapability(
            "focus_element",
            "Enfocar un elemento de UI",
            ["element_id"],
        )
        focus.preconditions = ["element_visible", "element_enabled"]
        focus.effects = ["element_focused"]
        focus.alternative_strategies = ["keyboard_shortcut", "hotkey"]
        self.ui_capabilities[focus.name] = focus

        click = UICapability(
            "click_element",
            "Hacer clic en un elemento de UI",
            ["element_id"],
        )
        click.preconditions = [
            "element_visible",
            "element_enabled",
            "element_focused",
        ]
        click.effects = ["element_clicked", "action_executed"]
        click.alternative_strategies = ["keyboard_shortcut", "hotkey"]
        self.ui_capabilities[click.name] = click

        type_cap = UICapability(
            "type_in_element",
            "Escribir texto en un elemento de UI",
            ["element_id"],
        )
        type_cap.preconditions = ["element_focused", "element_editable"]
        type_cap.effects = ["text_typed", "element_updated"]
        type_cap.alternative_strategies = ["keyboard_shortcut", "paste"]
        self.ui_capabilities[type_cap.name] = type_cap

    # ------------------------------------------------------------------
    # CARGA DE CONOCIMIENTO
    # ------------------------------------------------------------------

    @property
    def macros_coords_path(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "macros_coords.json"
        )

    def _load_ui_knowledge(self) -> None:
        path = self.macros_coords_path
        if not path.exists():
            logger._print_log("info", "Procesando solicitud", "coordinate_manager.py", "method", 322)
            return

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if not isinstance(data, dict):
                logger._print_log("warning", r"[COORDINATE-MANAGER] macros_coords.json no contiene un objeto [file:coordinate_manager.py, method:load_ui_knowledge, line:332]", "coordinate_manager.py", "method", 330)
                return

            self.ui_knowledge = data.get("ui_knowledge", {}) or {}
            self.calibration_policies = data.get("calibration_policies", {}) or {}

            if isinstance(self.ui_knowledge, dict):
                self._process_ui_knowledge()

            # El formato oficial conserva las calibraciones bajo "calibraciones".
            # Se carga además el formato legacy cuando está presente.
            self.load_from_macros_coords(data)

        except (OSError, json.JSONDecodeError) as exc:
            logger._print_log("error", r"[COORDINATE-MANAGER] Error cargando %s: %s [file:coordinate_manager.py, method:load_ui_knowledge, line:344]", "coordinate_manager.py", "method", 344)

    def _process_ui_knowledge(self) -> None:
        for app_name, app_data in self.ui_knowledge.items():
            if not isinstance(app_data, dict):
                continue
            for element_name, element_data in app_data.items():
                if not isinstance(element_data, dict):
                    continue
                resource = self._create_resource_from_knowledge(
                    f"{app_name}.{element_name}",
                    str(app_name),
                    str(element_name),
                    element_data,
                )
                if resource is not None:
                    self.register_ui_resource(resource)

    def _create_resource_from_knowledge(
        self,
        resource_id: str,
        app_name: str,
        element_name: str,
        element_data: Dict[str, Any],
    ) -> Optional[UIResource]:
        try:
            element_type = str(element_data.get("type", "element"))
            description = str(element_data.get("description", ""))
            strategy_name = str(
                element_data.get(
                    "calibration_strategy", CalibrationStrategy.VISUAL_DETECTION.value
                )
            )
            confidence = element_data.get("confidence", 0.8)

            try:
                strategy = CalibrationStrategy(strategy_name)
            except ValueError:
                strategy = CalibrationStrategy.VISUAL_DETECTION

            coordinates, regions = self._parse_screen_data(element_data)
            return UIResource(
                id=resource_id,
                name=element_name,
                resource_type=self._resource_type_for_element(element_type),
                application=app_name,
                element_type=element_type,
                calibration_strategy=strategy,
                calibrated_coordinates=coordinates,
                calibrated_regions=regions,
                confidence=float(confidence),
                is_available=bool(coordinates or regions),
                is_calibrated=bool(coordinates or regions),
                last_calibration_time=element_data.get("last_calibration_time"),
                description=description,
                alternatives=list(element_data.get("alternatives", []) or []),
                fallback_strategies=list(
                    element_data.get("fallback_strategies", []) or []
                ),
                requirements=list(element_data.get("requirements", []) or []),
                metadata=dict(element_data),
            )
        except (TypeError, ValueError) as exc:
            logger._print_log("error", r"[COORDINATE-MANAGER] Error creando recurso %s: %s [file:coordinate_manager.py, method:create_resource, line:407]", "coordinate_manager.py", "method", 407)
            return None

    @staticmethod
    def _resource_type_for_element(element_type: str) -> ResourceType:
        return (
            ResourceType.REGION
            if element_type.lower() == "region"
            else ResourceType.ELEMENT
        )

    def _parse_screen_data(
        self,
        element_data: Dict[str, Any],
    ) -> Tuple[Dict[int, Tuple[int, int]], Dict[int, Tuple[int, int, int, int]]]:
        coordinates: Dict[int, Tuple[int, int]] = {}
        regions: Dict[int, Tuple[int, int, int, int]] = {}

        screens_data = element_data.get("screens")
        if screens_data is None:
            screens_data = element_data.get("coordinates")

        if not isinstance(screens_data, dict):
            return coordinates, regions

        for screen_key, value in screens_data.items():
            screen_number = self.get_screen_number_from_key(str(screen_key))
            if screen_number is None:
                continue

            parsed = self._read_coordinate_value(value)
            if parsed is None:
                continue

            # En el formato sN de macros_coords, una pareja es siempre un punto.
            # La rama de regiones se reserva para datos explícitamente declarados
            # como bbox/region en metadata, evitando clasificar erróneamente [x,y].
            if (
                isinstance(value, (list, tuple))
                and len(value) >= 4
                and element_data.get("coordinate_kind") == "region"
            ):
                regions[screen_number] = (
                    int(value[0]),
                    int(value[1]),
                    int(value[2]),
                    int(value[3]),
                )
            else:
                coordinates[screen_number] = parsed

        explicit_regions = element_data.get("regions")
        if isinstance(explicit_regions, dict):
            for screen_key, value in explicit_regions.items():
                screen_number = self.get_screen_number_from_key(str(screen_key))
                if screen_number is None:
                    continue
                if isinstance(value, (list, tuple)) and len(value) >= 4:
                    try:
                        regions[screen_number] = (
                            int(value[0]),
                            int(value[1]),
                            int(value[2]),
                            int(value[3]),
                        )
                    except (TypeError, ValueError):
                        continue

        return coordinates, regions

    # ------------------------------------------------------------------
    # RECURSOS UI
    # ------------------------------------------------------------------

    def register_ui_resource(self, resource: UIResource) -> bool:
        try:
            self.ui_resources[resource.id] = resource
            logger._print_log("info", "Procesando solicitud", "coordinate_manager.py", "method", 322)
            return True
        except Exception as exc:
            logger._print_log("error", r"[COORDINATE-MANAGER] Error registrando recurso %s: %s [file:coordinate_manager.py, method:register_resource, line:487]", "coordinate_manager.py", "method", 487)
            return False

    def get_ui_resource(self, resource_id: str) -> Optional[UIResource]:
        if not resource_id:
            return None
        return self.ui_resources.get(str(resource_id).strip())

    def get_available_resources(
        self, application: Optional[str] = None
    ) -> List[UIResource]:
        app_filter = str(application).strip().lower() if application else None
        return [
            resource
            for resource in self.ui_resources.values()
            if resource.is_usable
            and (app_filter is None or resource.application.lower() == app_filter)
        ]

    def find_resources_by_type(
        self,
        resource_type: ResourceType,
        application: Optional[str] = None,
    ) -> List[UIResource]:
        app_filter = str(application).strip().lower() if application else None
        return [
            resource
            for resource in self.ui_resources.values()
            if resource.resource_type == resource_type
            and resource.is_usable
            and (app_filter is None or resource.application.lower() == app_filter)
        ]

    def has_resource(self, resource_id: str) -> bool:
        resource = self.get_ui_resource(resource_id)
        return bool(resource and resource.is_usable)

    def get_resource_alternatives(self, resource_id: str) -> List[UIResource]:
        resource = self.get_ui_resource(resource_id)
        if resource is None:
            return []
        return [
            alt
            for alt_id in resource.alternatives
            for alt in [self.get_ui_resource(alt_id)]
            if alt is not None and alt.is_usable
        ]

    def get_fallback_strategies(self, resource_id: str) -> List[str]:
        resource = self.get_ui_resource(resource_id)
        return list(resource.fallback_strategies) if resource else []

    # ------------------------------------------------------------------
    # CAPACIDADES
    # ------------------------------------------------------------------

    def get_capabilities_for_resources(
        self, resource_ids: List[str]
    ) -> List[UICapability]:
        available = set(resource_ids or [])
        return [
            capability
            for capability in self.ui_capabilities.values()
            if capability.can_execute_with_resources(available)
        ]

    def can_execute_capability(
        self, capability_name: str, resource_ids: List[str]
    ) -> bool:
        capability = self.ui_capabilities.get(str(capability_name).strip())
        return bool(
            capability
            and capability.can_execute_with_resources(set(resource_ids or []))
        )

    def get_capability_alternatives(self, capability_name: str) -> List[UICapability]:
        capability = self.ui_capabilities.get(str(capability_name).strip())
        if capability is None:
            return []
        return [
            alt
            for alt_name in capability.alternative_strategies
            for alt in [self.ui_capabilities.get(alt_name)]
            if alt is not None
        ]

    # ------------------------------------------------------------------
    # POLÍTICA DE CALIBRACIÓN
    # ------------------------------------------------------------------

    def get_calibration_strategy(
        self,
        application: str,
        element_type: str,
    ) -> Optional[CalibrationStrategy]:
        """
        Devuelve la estrategia permitida para una aplicación/elemento.

        La política es allow-by-default: una aplicación solo queda bloqueada
        aquí cuando la configuración la bloquea explícitamente. Esto permite
        que el sistema universal trabaje con aplicaciones nuevas sin añadirlas
        a una lista fija. Las restricciones de seguridad más amplias pertenecen
        al preflight de CalibrationManager.
        """
        app_lower = str(application or "").strip().lower()
        element_lower = str(element_type or "").strip().lower()
        if not app_lower:
            return None

        blocked = self.calibration_policies.get("blocked_applications", []) or []
        if any(str(item).strip().lower() in app_lower for item in blocked):
            logger._print_log("warning", r"[COORDINATE-MANAGER] Aplicación bloqueada para calibración: %s [file:coordinate_manager.py, method:get_calibration_policy, line:598]", "coordinate_manager.py", "method", 598)
            return None

        rules = self.calibration_policies.get("auto_calibration_rules", {}) or {}
        if isinstance(rules, dict) and app_lower in {
            str(k).lower(): v for k, v in rules.items()
        }:
            normalized_rules = {
                str(k).strip().lower(): bool(v) for k, v in rules.items()
            }
            if not normalized_rules.get(app_lower, True):
                return None

        mapping = {
            "button": CalibrationStrategy.VISUAL_DETECTION,
            "input": CalibrationStrategy.VISUAL_DETECTION,
            "field": CalibrationStrategy.VISUAL_DETECTION,
            "menu": CalibrationStrategy.VISUAL_DETECTION,
            "link": CalibrationStrategy.VISUAL_DETECTION,
            "checkbox": CalibrationStrategy.VISUAL_DETECTION,
            "radio": CalibrationStrategy.VISUAL_DETECTION,
            "select": CalibrationStrategy.VISUAL_DETECTION,
            "toolbar": CalibrationStrategy.VISUAL_DETECTION,
            "address_bar": CalibrationStrategy.VISUAL_DETECTION,
            "window": CalibrationStrategy.WINDOW_DETECTION,
            "region": CalibrationStrategy.SCREEN_CAPTURE,
        }
        return mapping.get(element_lower, CalibrationStrategy.VISUAL_DETECTION)

    def is_application_calibrable(self, application: str) -> bool:
        return self.get_calibration_strategy(application, "general") is not None

    def can_calibrate_element(self, application: str, element_type: str) -> bool:
        return self.get_calibration_strategy(application, element_type) is not None

    # ------------------------------------------------------------------
    # PLANIFICADOR / EJECUCIÓN
    # ------------------------------------------------------------------

    def get_execution_strategy_for_action(
        self,
        action_id: str,
        resource_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        strategy: Dict[str, Any] = {
            "action_id": action_id,
            "resource_id": resource_id,
            "primary_strategy": "direct_execution",
            "fallback_strategies": [],
            "resource_available": False,
            "alternative_resources": [],
            "alternative_methods": [],
        }

        if resource_id:
            resource = self.get_ui_resource(resource_id)
            if resource and resource.is_usable:
                strategy["resource_available"] = True
                strategy["primary_strategy"] = "ui_element"
                strategy["alternative_resources"] = [
                    alt.id for alt in self.get_resource_alternatives(resource_id)
                ]
                strategy["alternative_methods"] = self.get_fallback_strategies(
                    resource_id
                )
            return strategy

        action_lower = str(action_id or "").lower()
        if action_lower.startswith(("focus_", "click_", "type_")):
            for resource in self.find_resources_by_type(ResourceType.ELEMENT):
                if action_lower in {
                    str(item).lower() for item in resource.fallback_strategies
                }:
                    strategy["alternative_resources"].append(resource.id)
                    strategy["resource_available"] = True
                    strategy["primary_strategy"] = "ui_element"
                    continue
                if (
                    resource.element_type
                    and resource.element_type.lower() in action_lower
                ):
                    strategy["alternative_resources"].append(resource.id)
                    strategy["resource_available"] = True
                    strategy["primary_strategy"] = "ui_element"

        return strategy

    def get_resource_coordinates(
        self,
        resource_id: str,
        screen_number: Optional[int] = None,
    ) -> Optional[Tuple[int, int]]:
        resource = self.get_ui_resource(resource_id)
        if resource is None or not resource.is_usable:
            return None

        if screen_number is not None:
            coords = resource.get_coordinates_for_screen(screen_number)
            if coords is not None:
                return coords

        return resource.get_best_coordinates()

    def validate_resource_for_action(self, action_id: str, resource_id: str) -> bool:
        resource = self.get_ui_resource(resource_id)
        if resource is None or not resource.is_usable:
            return False

        action_lower = str(action_id or "").lower()
        element_type = resource.element_type.lower()

        if action_lower.startswith("focus_"):
            return element_type in {"input", "address_bar", "field", "text", "element"}

        if action_lower.startswith("click_"):
            return element_type in {
                "button",
                "element",
                "link",
                "menu",
                "checkbox",
                "radio",
                "select",
                "toolbar",
            }

        if action_lower.startswith("type_"):
            return element_type in {"input", "address_bar", "field", "text"}

        return True

    # ------------------------------------------------------------------
    # MACROS_COORDS.JSON
    # ------------------------------------------------------------------

    def load_from_macros_coords(self, calibration_data: Dict[str, Any]) -> int:
        """Carga recursos desde ``calibraciones`` o, para compatibilidad, desde ``legacy_data.macros``."""
        if not isinstance(calibration_data, dict):
            return 0

        calibraciones = calibration_data.get("calibraciones")
        if not isinstance(calibraciones, dict):
            legacy_data = calibration_data.get("legacy_data", {})
            if isinstance(legacy_data, dict):
                calibraciones = legacy_data.get("macros", {})
            else:
                calibraciones = {}

        loaded_count = 0
        for app_name, app_data in calibraciones.items():
            if not isinstance(app_data, dict):
                continue

            for element_name, element_data in app_data.items():
                if not isinstance(element_data, dict):
                    continue

                resource_id = f"{app_name}.{element_name}"
                resource = self._create_legacy_resource(
                    resource_id,
                    str(app_name),
                    str(element_name),
                    element_data,
                )
                if resource is None:
                    continue

                self.register_ui_resource(resource)
                loaded_count += 1

        logger._print_log("info", r"[COORDINATE-MANAGER] Cargados %s recursos desde calibraciones [file:coordinate_manager.py, method:load_calibration_data, line:768]", "coordinate_manager.py", "method", 768)
        return loaded_count

    def _create_legacy_resource(
        self,
        resource_id: str,
        app_name: str,
        element_name: str,
        element_data: Dict[str, Any],
    ) -> Optional[UIResource]:
        coordinates: Dict[int, Tuple[int, int]] = {}
        regions: Dict[int, Tuple[int, int, int, int]] = {}

        for screen_key, value in element_data.items():
            screen_number = self.get_screen_number_from_key(str(screen_key))
            if screen_number is None:
                continue

            if isinstance(value, (list, tuple)) and len(value) >= 2:
                try:
                    coordinates[screen_number] = (int(value[0]), int(value[1]))
                except (TypeError, ValueError):
                    continue

        is_calibrated = bool(coordinates or regions)
        return UIResource(
            id=resource_id,
            name=element_name,
            resource_type=ResourceType.ELEMENT,
            application=app_name,
            element_type=self._infer_element_type(element_name),
            calibration_strategy=CalibrationStrategy.VISUAL_DETECTION,
            calibrated_coordinates=coordinates,
            calibrated_regions=regions,
            confidence=0.8,
            is_available=is_calibrated,
            is_calibrated=is_calibrated,
            description=f"Elemento {element_name} de {app_name}",
            metadata={"source": "macros_coords.json"},
        )

    def _infer_element_type(self, element_name: str) -> str:
        name_lower = str(element_name or "").lower()
        if any(keyword in name_lower for keyword in ("button", "btn", "botón")):
            return "button"
        if any(
            keyword in name_lower
            for keyword in ("input", "field", "campo", "text", "address", "bar")
        ):
            return "input"
        if any(keyword in name_lower for keyword in ("menu", "menú")):
            return "menu"
        if any(keyword in name_lower for keyword in ("login", "inicio", "acceso")):
            return "login"
        return "element"

    # ------------------------------------------------------------------
    # COMPATIBILIDAD
    # ------------------------------------------------------------------

    def get_calibrated_coordinate(
        self,
        calibration_data: Dict[str, Any],
        application_name: str,
        element_name: str,
        screen_number: Optional[int] = None,
    ) -> Optional[Tuple[int, int]]:
        resource_id = f"{application_name}.{element_name}"
        resource = self.get_ui_resource(resource_id)
        if resource is not None:
            if screen_number is not None:
                return resource.get_coordinates_for_screen(screen_number)
            return resource.get_best_coordinates()

        return self._get_legacy_calibrated_coordinate(
            calibration_data,
            application_name,
            element_name,
            screen_number,
        )

    def _get_legacy_calibrated_coordinate(
        self,
        calibration_data: Dict[str, Any],
        application_name: str,
        element_name: str,
        screen_number: Optional[int] = None,
    ) -> Optional[Tuple[int, int]]:
        if not isinstance(calibration_data, dict):
            return None

        calibraciones = calibration_data.get("calibraciones", {})
        if not isinstance(calibraciones, dict):
            return None

        app_data = self._case_insensitive_dict_get(calibraciones, application_name)
        if not isinstance(app_data, dict):
            return None

        element_data = self._case_insensitive_dict_get(app_data, element_name)
        if not isinstance(element_data, dict):
            return None

        if screen_number is not None:
            screen_key = self.get_screen_key(screen_number)
            value = self._case_insensitive_dict_get(element_data, screen_key)
            return self._read_coordinate_value(value)

        for key in sorted(element_data, key=str):
            parsed = self._read_coordinate_value(element_data[key])
            if parsed is not None:
                return parsed

        return None

    @staticmethod
    def _case_insensitive_dict_get(data: Dict[str, Any], key: str) -> Any:
        target = str(key or "").strip().lower()
        for current_key, value in data.items():
            if str(current_key).strip().lower() == target:
                return value
        return None

    @staticmethod
    def monitor_number_from_object(monitor: Any) -> Optional[int]:
        """Extrae un número de monitor sin asumir un atributo concreto."""
        if monitor is None:
            return None

        screen_key = getattr(monitor, "screen_key", None)
        if isinstance(screen_key, str) and screen_key.lower().startswith("s"):
            number = CoordinateManager.screen_number_from_key(screen_key)
            if number is not None:
                return number

        for attr in ("screen_number", "number", "monitor_number"):
            value = getattr(monitor, attr, None)
            if isinstance(value, int) and value > 0:
                return value

        index = getattr(monitor, "index", None)
        if isinstance(index, int):
            # Los objetos MonitorInfo de JARVIS pueden exponer índice 1-based.
            if index > 0:
                return index
            if index == 0:
                return 1

        monitor_id = getattr(monitor, "monitor_id", None)
        if isinstance(monitor_id, str):
            number = CoordinateManager.screen_number_from_key(monitor_id)
            if number is not None:
                return number

        return None

    def get_screen_key(self, screen_number: int) -> str:
        return f"s{int(screen_number)}"

    @staticmethod
    def screen_number_from_key(screen_key: str) -> Optional[int]:
        if not isinstance(screen_key, str):
            return None
        value = screen_key.strip().lower()
        if not value.startswith("s") or not value[1:].isdigit():
            return None
        number = int(value[1:])
        return number if number > 0 else None

    def get_screen_number_from_key(self, screen_key: str) -> Optional[int]:
        return self.screen_number_from_key(screen_key)

    @staticmethod
    def _read_coordinate_value(value: Any) -> Optional[Tuple[int, int]]:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        try:
            x = int(value[0])
            y = int(value[1])
        except (TypeError, ValueError):
            return None
        return x, y

    # ------------------------------------------------------------------
    # VALIDACIÓN Y VENTANAS
    # ------------------------------------------------------------------

    def validate_coordinates(
        self,
        x: int,
        y: int,
        screen_width: int,
        screen_height: int,
    ) -> bool:
        try:
            return 0 <= int(x) < int(screen_width) and 0 <= int(y) < int(screen_height)
        except (TypeError, ValueError):
            return False

    def validate_bounding_box(
        self,
        bbox: BoundingBox,
        screen_width: int,
        screen_height: int,
    ) -> bool:
        try:
            return (
                bbox.width > 0
                and bbox.height > 0
                and bbox.x >= 0
                and bbox.y >= 0
                and bbox.right <= int(screen_width)
                and bbox.bottom <= int(screen_height)
            )
        except (TypeError, ValueError, AttributeError):
            return False

    def get_window_bounding_box(self, window_title: str) -> Optional[BoundingBox]:
        """Compatibilidad legacy: obtiene una ventana por título.

        Cuando la ventana está minimizada, intenta obtener su posición normal
        mediante Win32 en vez de confiar exclusivamente en ``pygetwindow``.
        """
        try:
            windows = gw.getWindowsWithTitle(str(window_title or ""))
        except Exception as exc:
            logger._print_log("error", r"[COORDINATE-MANAGER] Error buscando ventana %s: %s [file:coordinate_manager.py, method:find_window_by_title, line:994]", "coordinate_manager.py", "method", 994)
            return None

        for window in windows or []:
            try:
                visible = getattr(window, "is_visible", True)
                if callable(visible):
                    visible = visible()
                # No descartamos una ventana minimizada: es precisamente uno
                # de los casos donde pygetwindow puede devolver geometría mala.
                if visible is False and not bool(getattr(window, "isMinimized", False)):
                    continue

                rect = self._get_window_rect(window)
                if rect is not None:
                    return rect
            except Exception:
                continue

        if windows:
            logger._print_log("warning", r"[COORDINATE-MANAGER] No se pudo obtener geometría válida para %s [file:coordinate_manager.py, method:find_window_by_title, line:1014]", "coordinate_manager.py", "method", 1014)
        else:
            logger._print_log("warning", r"[COORDINATE-MANAGER] Ventana no encontrada: %s [file:coordinate_manager.py, method:find_window_by_title, line:1019]", "coordinate_manager.py", "method", 1016)
        return None

    @staticmethod
    def _get_window_rect(window: Any) -> Optional[BoundingBox]:
        """Obtiene geometría de ventana priorizando el rectángulo normal de Win32."""
        hwnd = getattr(window, "_hWnd", None)
        if hwnd is None:
            hwnd = getattr(window, "hwnd", None)

        if isinstance(hwnd, int) and hwnd > 0 and os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                class RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", wintypes.LONG),
                        ("top", wintypes.LONG),
                        ("right", wintypes.LONG),
                        ("bottom", wintypes.LONG),
                    ]

                class POINT(ctypes.Structure):
                    _fields_ = [
                        ("x", wintypes.LONG),
                        ("y", wintypes.LONG),
                    ]

                class WINDOWPLACEMENT(ctypes.Structure):
                    _fields_ = [
                        ("length", wintypes.UINT),
                        ("flags", wintypes.UINT),
                        ("showCmd", wintypes.UINT),
                        ("ptMinPosition", POINT),
                        ("ptMaxPosition", POINT),
                        ("rcNormalPosition", RECT),
                    ]

                user32 = ctypes.windll.user32
                user32.GetWindowPlacement.argtypes = [
                    wintypes.HWND,
                    ctypes.POINTER(WINDOWPLACEMENT),
                ]
                user32.GetWindowPlacement.restype = wintypes.BOOL

                placement = WINDOWPLACEMENT()
                placement.length = ctypes.sizeof(WINDOWPLACEMENT)

                if user32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
                    rect = placement.rcNormalPosition
                    width = int(rect.right - rect.left)
                    height = int(rect.bottom - rect.top)
                    if width > 0 and height > 0:
                        return BoundingBox(
                            x=int(rect.left),
                            y=int(rect.top),
                            width=width,
                            height=height,
                        )
            except Exception:
                pass

        try:
            left = int(getattr(window, "left", 0))
            top = int(getattr(window, "top", 0))
            width = int(getattr(window, "width", 0))
            height = int(getattr(window, "height", 0))
            if width > 0 and height > 0:
                return BoundingBox(left, top, width, height)
        except (TypeError, ValueError):
            return None

        return None


_coordinate_manager: Optional[CoordinateManager] = None


def get_coordinate_manager() -> CoordinateManager:
    """Obtiene la instancia global del gestor de coordenadas."""
    global _coordinate_manager
    if _coordinate_manager is None:
        _coordinate_manager = CoordinateManager()
    return _coordinate_manager


__all__ = [
    "ResourceType",
    "CalibrationStrategy",
    "UIResource",
    "UICapability",
    "CoordinateSystem",
    "BoundingBox",
    "ElementInfo",
    "CoordinateManager",
    "get_coordinate_manager",
]
