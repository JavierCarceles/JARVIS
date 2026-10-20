"""
Fachada y capacidades de calibración para JARVIS.

Este módulo mantiene la API histórica de ``Calibrator`` y la capa de
capacidades jerárquicas, pero delega la calibración real en
``CalibrationManager``.

La calibración global no depende de una aplicación concreta: el manager es la
fuente de verdad para descubrimiento, preparación, monitor, captura y
persistencia. Este módulo no abre, mueve ni cierra Chrome de forma especial.
"""

from __future__ import annotations

import inspect
import platform
import re
import sys
import time
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..utils.config import get_calibration_config
from ..utils.logger import get_logger
from ..utils.screen_manager import get_screen_manager

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.hands.planner.node import Goal, Node


class CalibrationPolicy(Enum):
    NEVER = "never"
    ASK = "ask"
    AUTOMATIC = "automatic"
    REQUIRED = "required"


class CalibrationStatus(Enum):
    UNKNOWN = "unknown"
    NOT_CALIBRATED = "not_calibrated"
    CALIBRATED = "calibrated"
    OUTDATED = "outdated"
    INVALID = "invalid"


@dataclass
class CalibrationElement:
    id: str
    name: str
    application: str
    element_type: str
    coordinates: Optional[Dict[str, Tuple[int, int]]] = None
    calibration_status: CalibrationStatus = CalibrationStatus.UNKNOWN
    last_calibrated: Optional[float] = None
    confidence: float = 0.0
    alternatives: List[str] = field(default_factory=list)
    requires_focus: bool = True
    policy: CalibrationPolicy = CalibrationPolicy.ASK


@dataclass
class CalibrationCapability:
    id: str
    name: str
    description: str
    supported_elements: List[str]
    calibration_method: str
    success_criteria: List[str]
    estimated_cost: float = 1.0
    reliability: float = 0.9


class CalibrationStrategy(ABC):
    @abstractmethod
    def can_calibrate(self, element: CalibrationElement) -> bool:
        raise NotImplementedError

    @abstractmethod
    def calibrate(self, element: CalibrationElement) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_applicable_applications(self) -> List[str]:
        raise NotImplementedError


class UniversalVisualCalibrationStrategy(CalibrationStrategy):
    """Estrategia visual delegada por completo al CalibrationManager."""

    def __init__(self) -> None:
        logger._print_log("info", r"Inicializando UniversalVisualCalibrationStrategy [file:calibrator.py, method:__init__, line:96]", "calibrator.py", "method", 96)
        self.calibration_manager = self._get_calibration_manager()

    def can_calibrate(self, element: CalibrationElement) -> bool:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        if element.policy == CalibrationPolicy.NEVER:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
            return False
        can_calibrate_result = element.element_type.casefold() not in {
            "game",
            "ide",
            "terminal",
            "console",
        }
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "can_calibrate", 110)
        return can_calibrate_result

    def calibrate(self, element: CalibrationElement) -> Dict[str, Any]:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)

        if element.calibration_status == CalibrationStatus.CALIBRATED:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
            return {
                "success": True,
                "message": "Ya calibrado",
                "element_id": element.id,
                "status": CalibrationStatus.CALIBRATED.value,
            }

        try:
            manager = self.calibration_manager
            method = getattr(manager, "calibrate_application", None)
            if not callable(method):
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) para elemento: {element.id}", "calibrator.py", "calibrate", 129)
                return {
                    "success": False,
                    "message": "CalibrationManager no expone calibrate_application()",
                    "element_id": element.id,
                }

            monitor_number = self._resolve_monitor_number(element)
            if monitor_number is None:
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
                return {
                    "success": False,
                    "message": "No se pudo determinar el monitor para el elemento",
                    "element_id": element.id,
                }

            result = method(element.application, monitor_number)
            result_dict = self._result_to_dict(result)
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)}", "calibrator.py", "calibrate", 147)
            if not result_dict.get("success"):
                error_msg = result_dict.get("error", result_dict.get("error_message", "Error desconocido"))
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
                return {
                    "success": False,
                    "message": error_msg,
                    "element_id": element.id,
                }

            coordinates = self._find_element_coordinates(
                result_dict, element.name, monitor_number
            )
            if coordinates is None:
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
                return {
                    "success": False,
                    "message": f"No se encontró el elemento '{element.name}' en la calibración",
                    "element_id": element.id,
                }

            element.coordinates = coordinates
            element.calibration_status = CalibrationStatus.CALIBRATED
            element.last_calibrated = float(
                result_dict.get("timestamp", time.time()) or time.time()
            )
            element.confidence = self._find_element_confidence(
                result_dict, element.name
            )
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate", 176)

            return {
                "success": True,
                "message": "Calibración exitosa",
                "element_id": element.id,
                "coordinates": element.coordinates,
                "confidence": element.confidence,
                "monitor": monitor_number,
            }

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate", 188)
            element.calibration_status = CalibrationStatus.INVALID
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate", 193)
            return {
                "success": False,
                "message": str(exc),
                "element_id": element.id,
            }

    def _resolve_monitor_number(self, element: CalibrationElement) -> Optional[int]:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        """Obtiene el monitor asociado o, como último recurso, el monitor activo."""
        if element.coordinates:
            keys = [key for key in element.coordinates if re.fullmatch(r"s\d+", str(key).casefold())]
            if keys:
                try:
                    monitor_num = int(str(keys[0])[1:])
                    logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "_resolve_monitor_number", 205)
                    return monitor_num
                except (TypeError, ValueError):
                    logger._print_log("warning", r"No se pudo parsear número de monitor desde coordenadas [file:calibrator.py, method:_resolve_monitor_number, line:211]", "calibrator.py", "method", 208)
                    pass

        manager = self.calibration_manager
        monitors = list(getattr(manager.screen_manager, "monitors", []) or [])
        if not monitors:
            return None

        active = getattr(manager.screen_manager, "get_active_monitor", lambda: None)()
        if active is not None:
            return int(active.monitor_id)
        primary = getattr(manager.screen_manager, "get_primary_monitor", lambda: None)()
        if primary is not None:
            return int(primary.monitor_id)
        return int(monitors[0].monitor_id)

    def get_applicable_applications(self) -> List[str]:
        try:
            manager = self.calibration_manager
            method = getattr(manager, "get_available_applications", None)
            if callable(method):
                return [str(value) for value in method() if str(value).strip()]
            method = getattr(manager, "get_supported_applications", None)
            if callable(method):
                return [str(value) for value in method() if str(value).strip()]
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "_get_available_applications", 234)
        return []

    @staticmethod
    def _result_to_dict(result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return result
        if hasattr(result, "to_dict") and callable(result.to_dict):
            try:
                value = result.to_dict()
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
        if hasattr(result, "__dict__"):
            return dict(vars(result))
        return {}

    def _find_element_coordinates(
        self,
        result: Dict[str, Any],
        element_name: str,
        monitor_number: int,
    ) -> Optional[Dict[str, Tuple[int, int]]]:
        target = self._normalize_element_name(element_name)
        data = result.get("calibration_data")
        if not isinstance(data, dict):
            data = result
        elements = data.get("elements", [])
        if not isinstance(elements, list):
            return None

        for element in elements:
            if not isinstance(element, dict):
                continue
            name = self._normalize_element_name(
                element.get("name") or element.get("text")
            )
            if name != target:
                continue
            center = element.get("center")
            if isinstance(center, (list, tuple)) and len(center) >= 2:
                try:
                    return {
                        f"s{int(monitor_number)}": (
                            int(round(float(center[0]))),
                            int(round(float(center[1]))),
                        )
                    }
                except (TypeError, ValueError):
                    return None
        return None

    @classmethod
    def _find_element_confidence(cls, result: Dict[str, Any], element_name: str) -> float:
        data = result.get("calibration_data")
        if not isinstance(data, dict):
            data = result
        elements = data.get("elements", [])
        target = cls._normalize_element_name(element_name)
        if isinstance(elements, list):
            for element in elements:
                if not isinstance(element, dict):
                    continue
                name = cls._normalize_element_name(
                    element.get("name") or element.get("text")
                )
                if name == target:
                    try:
                        return max(
                            0.0,
                            min(1.0, float(element.get("confidence", 0.0))),
                        )
                    except (TypeError, ValueError):
                        return 0.0
        return 0.0

    @staticmethod
    def _normalize_element_name(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text)).strip("_")

    @staticmethod
    def _get_calibration_manager():
        from .calibration_manager import get_calibration_manager

        return get_calibration_manager()


class KeyboardShortcutStrategy(CalibrationStrategy):
    """Estrategia alternativa basada en atajos de teclado."""

    def can_calibrate(self, element: CalibrationElement) -> bool:
        return bool(element.alternatives)

    def calibrate(self, element: CalibrationElement) -> Dict[str, Any]:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        return {
            "success": True,
            "message": "Requiere ejecución de atajo de teclado",
            "element_id": element.id,
            "strategy": "keyboard_shortcut",
            "alternatives": list(element.alternatives),
        }

    def get_applicable_applications(self) -> List[str]:
        return []


class EnhancedCalibrator:
    """Sistema de capacidades de calibración compatible con el planner."""

    def __init__(self) -> None:
        logger._print_log("info", r"Inicializando Calibrator mejorado [file:calibrator.py, method:__init__, line:350]", "calibrator.py", "method", 347)
        self.screen_manager = get_screen_manager()
        self.calibration_config = get_calibration_config()
        self.elements: Dict[str, CalibrationElement] = {}
        self.calibration_manager = self._get_calibration_manager()
        self.strategies: List[CalibrationStrategy] = [
            UniversalVisualCalibrationStrategy(),
            KeyboardShortcutStrategy(),
        ]
        self.capabilities: Dict[str, CalibrationCapability] = {}
        self._initialize_capabilities()
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)} estrategias", "calibrator.py", "__init__", 361)

    def _initialize_capabilities(self) -> None:
        self.capabilities = {
            "calibrate_element": CalibrationCapability(
                id="calibrate_element",
                name="Calibrar Elemento UI",
                description="Calibra un elemento específico de una aplicación",
                supported_elements=["button", "input", "menu", "toolbar"],
                calibration_method="visual",
                success_criteria=["element_detected", "coordinates_obtained"],
                estimated_cost=2.0,
                reliability=0.9,
            ),
            "calibrate_application": CalibrationCapability(
                id="calibrate_application",
                name="Calibrar Aplicación",
                description="Calibra los elementos visibles de una aplicación",
                supported_elements=["window", "button", "input", "menu", "toolbar"],
                calibration_method="batch_visual",
                success_criteria=["elements_detected", "consistent_coordinates"],
                estimated_cost=5.0,
                reliability=0.85,
            ),
            "verify_calibration": CalibrationCapability(
                id="verify_calibration",
                name="Verificar Calibración",
                description="Verifica si los elementos calibrados siguen válidos",
                supported_elements=["button", "input", "menu"],
                calibration_method="verification",
                success_criteria=["element_detected", "coordinates_match"],
                estimated_cost=1.0,
                reliability=0.95,
            ),
            "find_alternative": CalibrationCapability(
                id="find_alternative",
                name="Encontrar Alternativa",
                description="Busca alternativas cuando falla la calibración",
                supported_elements=["button", "input", "menu"],
                calibration_method="strategy_alternative",
                success_criteria=["alternative_found", "alternative_usable"],
                estimated_cost=1.5,
                reliability=0.8,
            ),
        }

    def get_calibration_capability(self, capability_id: str) -> Optional[CalibrationCapability]:
        return self.capabilities.get(capability_id)

    def get_available_capabilities(self) -> List[CalibrationCapability]:
        return list(self.capabilities.values())

    def check_element_calibration(self, element_id: str) -> CalibrationStatus:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        element = self.elements.get(element_id)
        if not element:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
            return CalibrationStatus.UNKNOWN
        if element.calibration_status == CalibrationStatus.CALIBRATED and element.last_calibrated:
            if time.time() - element.last_calibrated > 3600:
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
                element.calibration_status = CalibrationStatus.OUTDATED
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        return element.calibration_status

    def can_use_element(self, element_id: str, current_state: Dict[str, Any]) -> bool:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "can_use_element", 424)
        status = self.check_element_calibration(element_id)
        if status == CalibrationStatus.CALIBRATED:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) + " está calibrado y puede usarse", "calibrator.py", "can_use_element", 427)
            return True
        if status == CalibrationStatus.OUTDATED:
            allow_outdated = bool(current_state.get("allow_outdated_calibration", False))
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
            return allow_outdated
        if status == CalibrationStatus.NOT_CALIBRATED:
            element = self.elements.get(element_id)
            can_automatic = bool(element and element.policy == CalibrationPolicy.AUTOMATIC)
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "can_use_element", 436)
            return can_automatic
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        return False

    def calibrate_element_if_needed(
        self,
        element_id: str,
        current_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate_element_if_needed", 449)
        element = self.elements.get(element_id)
        if not element:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate_element_if_needed", 452)
            return {"success": False, "error": "Elemento no encontrado", "element_id": element_id}

        status = self.check_element_calibration(element_id)
        if status == CalibrationStatus.CALIBRATED:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate_element_if_needed", 457)
            return {
                "success": True,
                "message": "Elemento ya calibrado",
                "element_id": element_id,
                "status": status.value,
            }

        if element.policy == CalibrationPolicy.NEVER:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) + " tiene política NEVER, no se puede calibrar", "calibrator.py", "calibrate_element_if_needed", 466)
            return {
                "success": False,
                "error": "Elemento tiene política NEVER",
                "element_id": element_id,
                "requires_alternative": True,
            }

        if element.policy == CalibrationPolicy.ASK and not current_state.get("allow_auto_calibration", False):
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) + " tiene política ASK y no se permite calibración automática", "calibrator.py", "calibrate_element_if_needed", 475)
            return {
                "success": False,
                "error": "Requiere confirmación manual",
                "element_id": element_id,
                "requires_confirmation": True,
            }

        for strategy in self.strategies:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100).__name__}", "calibrator.py", "calibrate_element_if_needed", 481)
            if not strategy.can_calibrate(element):
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100).__name__} no puede calibrar elemento: {element.id}", "calibrator.py", "calibrate_element_if_needed", 486)
                continue
            result = strategy.calibrate(element)
            if result.get("success"):
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100).__name__} calibró exitosamente elemento: {element.id}", "calibrator.py", "calibrate_element_if_needed", 490)
                return result
            else:
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100).__name__} falló al calibrar elemento: {element.id}", "calibrator.py", "calibrate_element_if_needed", 493)

        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) + ", buscando alternativas", "calibrator.py", "calibrate_element_if_needed", 495)
        return self._find_alternative_strategy(element)

    def _find_alternative_strategy(self, element: CalibrationElement) -> Dict[str, Any]:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        for strategy in self.strategies:
            if isinstance(strategy, KeyboardShortcutStrategy) and strategy.can_calibrate(element):
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100).__name__, "calibrator.py", "_find_alternative_strategy", 496)
                result = strategy.calibrate(element)
                if result.get("success"):
                    logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
                    return result
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        element.calibration_status = CalibrationStatus.INVALID
        return {
            "success": False,
            "error": "No se pudo calibrar y no hay alternativas disponibles",
            "element_id": element.id,
            "requires_alternative": True,
        }

    def register_element(self, element: CalibrationElement) -> None:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        self.elements[element.id] = element

    def get_element_coordinates(self, element_id: str) -> Optional[Dict[str, Tuple[int, int]]]:
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        element = self.elements.get(element_id)
        if element and element.calibration_status == CalibrationStatus.CALIBRATED:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
            return element.coordinates
        else:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        return None

    def create_calibration_node(self, element_id: str) -> Optional["Node"]:
        element = self.elements.get(element_id)
        if not element:
            return None
        try:
            from src.hands.planner.node import Node, NodeType
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "create_calibration_node", 535)
            return None

        return Node(
            id=f"calibrate.{element_id}",
            type=NodeType.ACTION,
            name=f"Calibrar {element.name}",
            description=f"Calibrar elemento {element.name} de {element.application}",
            preconditions=[f"{element.application}_open", "system_ready"],
            effects=[f"{element_id}_calibrated"],
            cost=1.0,
            parameters={"element_id": element_id},
            application=element.application,
            ui_element=element_id,
            execute_callback=self.calibrate_element_if_needed,
            metadata={
                "element_type": element.element_type,
                "calibration_policy": element.policy.value,
                "requires_focus": element.requires_focus,
            },
        )

    def get_calibration_requirements_for_goal(self, goal: "Goal") -> List[str]:
        logger._print_log("info", r"Obteniendo requisitos de calibración para goal [file:calibrator.py, method:get_calibration_requirements_for_goal, line:561]", "calibrator.py", "method", 557)
        required_elements: List[str] = []
        goal_to_elements = {
            "navigate": ["address_bar", "search_bar"],
            "open_application": ["app_window", "app_icon"],
            "click_element": ["target_button", "target_link"],
            "type_text": ["text_input", "address_bar"],
            "navigate_stream": ["stream_button", "watch_button"],
        }
        target = str(getattr(goal, "target", "") or "").strip().casefold()
        goal_type = str(getattr(goal, "type", "") or "").strip().casefold()
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        for element_type in goal_to_elements.get(goal_type, []):
            for element_id, element in self.elements.items():
                if (
                    element.element_type == element_type
                    and element.application.casefold() == target
                    and self.check_element_calibration(element_id) != CalibrationStatus.CALIBRATED
                ):
                    required_elements.append(element_id)
                    logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)) + " elementos", "calibrator.py", "get_calibration_requirements_for_goal", 583)
        return required_elements

    # ========================================================================
    # API GLOBAL / LEGACY
    # ========================================================================

    def calibrate_applications(
        self,
        app_name: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Entrada legacy y global compatible con CalibrationManager."""
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate_applications", 596)

        if not self._verify_system():
            logger._print_log("info", r"Sistema no compatible para calibración [file:calibrator.py, method:calibrate_applications, line:601]", "calibrator.py", "method", 594)
            return self._failure_report("Sistema no compatible")

        manager = self.calibration_manager
        try:
            if app_name:
                return self._calibrate_single_application(manager, str(app_name).strip(), force=force)

            method = getattr(manager, "calibrate_all_applications", None)
            if not callable(method):
                logger._print_log("info", r"CalibrationManager no expone calibrate_all_applications(, "calibrator.py", "method", 604) [file:calibrator.py, method:calibrate_applications, line:610]")
                return self._failure_report(
                    "CalibrationManager no expone calibrate_all_applications()"
                )

            result = self._call_global_manager(method, force=force)
            return self._normalize_global_result(result)
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "calibrate_applications", 617)
            return self._failure_report(str(exc))

    def _calibrate_single_application(
        self,
        manager: Any,
        app_name: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not force:
            method = getattr(manager, "is_application_calibrated", None)
            if callable(method):
                try:
                    if method(app_name):
                        return {
                            "success": True,
                            "application": app_name,
                            "applications_requested": 1,
                            "calibrated": [],
                            "skipped": [app_name],
                            "failed": [],
                            "monitors_detected": len(getattr(self.screen_manager, "monitors", []) or []),
                            "total_elements": 0,
                            "message": f"{app_name} ya estaba calibrada",
                        }
                except Exception:
                    pass

        method = getattr(manager, "calibrate_application", None)
        if not callable(method):
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) para aplicación: " + app_name, "calibrator.py", "_calibrate_single_application", 646)
            return self._single_failure_report(
                app_name, "CalibrationManager no expone calibrate_application()"
            )

        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
        self.screen_manager.refresh_monitors()
        monitors = list(getattr(self.screen_manager, "monitors", []) or [])
        if not monitors:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)
            return self._single_failure_report(app_name, "No se encontraron monitores")

        results: List[Any] = []
        for monitor in monitors:
            try:
                results.append(method(app_name, int(monitor.monitor_id)))
            except Exception as exc:
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) + ": " + str(exc), "calibrator.py", "_calibrate_single_application", 661)
                results.append({
                    "success": False,
                    "error": str(exc),
                    "screen_number": int(monitor.monitor_id),
                })

        return self._build_single_application_report(
            app_name, results, len(monitors)
        )

    def _build_single_application_report(
        self,
        app_name: str,
        results: List[Any],
        monitor_count: int,
    ) -> Dict[str, Any]:
        total_elements = 0
        success_results = 0
        errors: List[str] = []

        for result in results:
            normalized = self._result_to_dict(result)
            if normalized.get("success") and not normalized.get("skipped"):
                success_results += 1
                total_elements += self._extract_element_count(normalized)
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100)), "calibrator.py", "_normalize_single_result", 687)
            elif normalized.get("error") or normalized.get("error_message"):
                errors.append(str(normalized.get("error") or normalized.get("error_message")))
                logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) or normalized.get("error_message")), "calibrator.py", "_normalize_single_result", 690)

        calibrated = [app_name] if success_results else []
        failed = [] if calibrated else [app_name]
        logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100) + " con " + str(success_results) + " resultados exitosos", "calibrator.py", "_normalize_single_result", 693)
        report = {
            "success": bool(calibrated),
            "application": app_name,
            "applications_requested": 1,
            "calibrated": calibrated,
            "skipped": [],
            "failed": failed,
            "monitors_detected": monitor_count,
            "total_elements": total_elements,
            "results": results,
        }
        if errors:
            report["errors"] = list(dict.fromkeys(errors))
        return report

    @staticmethod
    def _call_global_manager(method: Any, force: bool) -> Any:
        try:
            signature = inspect.signature(method)
            if "force" in signature.parameters:
                return method(force=force)
            return method()
        except (TypeError, ValueError):
            try:
                return method(force=force)
            except TypeError:
                return method()

    def _normalize_global_result(self, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict) and self._looks_like_global_report(result):
            return result

        calibrated: List[str] = []
        skipped: List[str] = []
        failed: List[str] = []
        results_by_application: Dict[str, Any] = {}
        total_elements = 0

        if isinstance(result, dict):
            for raw_name, raw_results in result.items():
                app_name = str(raw_name).strip()
                key = self._normalize_name(app_name)
                results_by_application[key or app_name] = raw_results
                entries = raw_results if isinstance(raw_results, list) else [raw_results]
                app_success = False
                app_skipped = False
                for entry in entries:
                    normalized = self._result_to_dict(entry)
                    total_elements += self._extract_element_count(normalized)
                    if normalized.get("success"):
                        if normalized.get("skipped"):
                            app_skipped = True
                        else:
                            app_success = True
                if app_success:
                    calibrated.append(key or app_name)
                elif app_skipped:
                    skipped.append(key or app_name)
                else:
                    failed.append(key or app_name)

        monitor_count = len(getattr(self.screen_manager, "monitors", []) or [])
        return {
            "success": bool(calibrated or skipped) and not failed,
            "monitors_detected": monitor_count,
            "applications_requested": len(results_by_application),
            "calibrated": calibrated,
            "skipped": skipped,
            "failed": failed,
            "total_elements": total_elements,
            "results": results_by_application,
        }

    @staticmethod
    def _looks_like_global_report(value: Dict[str, Any]) -> bool:
        return {"calibrated", "skipped", "failed", "total_elements"}.issubset(value.keys())

    @staticmethod
    def _result_to_dict(result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return result
        if hasattr(result, "to_dict") and callable(result.to_dict):
            try:
                value = result.to_dict()
                return value if isinstance(value, dict) else {"result": value}
            except Exception:
                pass
        if hasattr(result, "__dict__"):
            return dict(vars(result))
        return {"result": result}

    @staticmethod
    def _extract_element_count(result: Dict[str, Any]) -> int:
        for key in ("total_elements", "elements_count", "element_count"):
            try:
                return max(0, int(result.get(key)))
            except (TypeError, ValueError):
                continue
        calibration_data = result.get("calibration_data")
        if isinstance(calibration_data, dict):
            elements = calibration_data.get("elements")
            if isinstance(elements, list):
                return len(elements)
            results = calibration_data.get("results")
            if isinstance(results, list):
                return sum(EnhancedCalibrator._extract_element_count(EnhancedCalibrator.__new__(EnhancedCalibrator), item) for item in results if isinstance(item, dict))
        return 0

    def calibrate_chrome_both_screens(self) -> Dict[str, Any]:
        """Compatibilidad legacy; delega en la misma API de aplicación."""
        logger._print_log("warning", r"[CALIBRATION] calibrate_chrome_both_screens(, "calibrator.py", "method", 803) es legacy [file:calibrator.py, method:calibrate_chrome_both_screens, line:803]")
        return self.calibrate_applications("chrome")

    def _verify_system(self) -> bool:
        try:
            if platform.system().casefold() != "windows" or sys.version_info < (3, 8):
                return False
            import ctypes  # noqa: F401
            import pyautogui  # noqa: F401
            import pygetwindow  # noqa: F401
            self.screen_manager.refresh_monitors()
            return len(getattr(self.screen_manager, "monitors", []) or []) > 0
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "_verify_system", 816)
            return False

    def get_calibration_statistics(self) -> Dict[str, Any]:
        total_elements = len(self.elements)
        status_counts = {
            status.value: sum(
                1 for element in self.elements.values() if element.calibration_status == status
            )
            for status in CalibrationStatus
        }
        supported_apps = set()
        try:
            supported_apps.update(UniversalVisualCalibrationStrategy().get_applicable_applications())
        except Exception:
            supported_apps.update(element.application for element in self.elements.values())
        return {
            "total_elements": total_elements,
            "calibration_status": status_counts,
            "available_capabilities": len(self.capabilities),
            "available_strategies": len(self.strategies),
            "supported_applications": sorted(supported_apps),
        }

    def _is_already_calibrated(self, app_name: str) -> bool:
        method = getattr(self.calibration_manager, "is_application_calibrated", None)
        if not callable(method):
            return False
        try:
            return bool(method(app_name))
        except Exception as exc:
            logger._print_log("warning", r"[CALIBRATOR] No se pudo consultar el estado de %s: %s [file:calibrator.py, method:is_application_capable, line:847]", "calibrator.py", "method", 847)
            return False

    def _save_organized_results(self, app_name: str, results: Dict[str, Any]) -> None:
        """Compatibilidad legacy; la persistencia pertenece al manager."""
        del results
        logger._print_log("debug", r"[CALIBRATOR] Persistencia delegada al CalibrationManager para %s [file:calibrator.py, method:_save_organized_results, line:853]", "calibrator.py", "method", 853)

    def _build_setup_info(self) -> Dict[str, Any]:
        setup = getattr(self.screen_manager, "setup", {})
        if isinstance(setup, dict):
            return {
                "type": setup.get("setup_type", "unknown"),
                "total_resolution": f"{setup.get('total_width', 0)}x{setup.get('total_height', 0)}",
                "multi_screen": bool(setup.get("is_multi_screen", False)),
                "screen_count": int(setup.get("screen_count", len(getattr(self.screen_manager, "monitors", []) or []))),
                "monitors": setup.get("monitors", []),
            }
        return {
            "type": getattr(getattr(setup, "setup_type", None), "value", "unknown"),
            "total_resolution": "0x0",
            "multi_screen": len(getattr(self.screen_manager, "monitors", []) or []) > 1,
            "screen_count": len(getattr(self.screen_manager, "monitors", []) or []),
            "monitors": [monitor.to_dict() for monitor in getattr(self.screen_manager, "monitors", []) or []],
        }

    def _has_calibration_command(self, app_name: str) -> bool:
        del app_name
        try:
            manager = self.calibration_manager
            return callable(getattr(manager, "calibrate_application", None))
        except Exception:
            return False

    def _open_app_on_monitor(self, app_name: str, monitor_num: int) -> bool:
        """Compatibilidad legacy con flujo genérico del CalibrationManager."""
        manager = self.calibration_manager
        try:
            self.screen_manager.refresh_monitors()
            monitor = self.screen_manager.get_monitor(int(monitor_num))
            if monitor is None:
                return False

            resolver = getattr(manager, "_resolve_application", None)
            if not callable(resolver):
                return False
            application = resolver(app_name)
            if not application:
                return False

            launcher = getattr(manager, "launch_application", None)
            mover = getattr(manager, "move_window_to_monitor", None)
            if not callable(launcher) or not callable(mover):
                return False

            _, launched_or_reused = launcher(application)
            if not launched_or_reused:
                return False
            window = getattr(manager, "_last_launch_window", None)
            return bool(window is not None and mover(window, int(monitor_num)))
        except Exception as exc:
            logger._print_log("debug", r"[CALIBRATOR] No se pudo preparar %s en monitor %s: %s [file:calibrator.py, method:_prepare_application, line:911]", "calibrator.py", "method", 908)
            return False

    def _close_app(self, app_name: str) -> bool:
        """Solo cierra recursos creados por el flujo de calibración, nunca una app del usuario por nombre."""
        del app_name
        manager = self.calibration_manager
        try:
            owned_hwnds = set(getattr(manager, "_last_launch_owned_hwnds", set()) or set())
            owned_pids = set(getattr(manager, "_last_launch_owned_pids", set()) or set())
            window = getattr(manager, "_last_launch_window", None)
            closer = getattr(manager, "_close_all_owned_windows", None)
            if window is None or not owned_hwnds or not callable(closer):
                return False
            return bool(closer(window, owned_hwnds, owned_pids))
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "calibrator.py", "method", 100), "calibrator.py", "_close_app", 924)
            return False

    def _get_calibration_manager(self):
        from .calibration_manager import get_calibration_manager
        return get_calibration_manager()

    @staticmethod
    def _normalize_name(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text)).strip("_")

    @staticmethod
    def _single_failure_report(app_name: str, error: str) -> Dict[str, Any]:
        return {
            "success": False,
            "application": app_name,
            "applications_requested": 1,
            "calibrated": [],
            "skipped": [],
            "failed": [app_name],
            "monitors_detected": 0,
            "total_elements": 0,
            "error": error,
        }

    @staticmethod
    def _failure_report(error: str) -> Dict[str, Any]:
        return {
            "success": False,
            "error": error,
            "monitors_detected": 0,
            "applications_requested": 0,
            "calibrated": [],
            "skipped": [],
            "failed": [],
            "total_elements": 0,
        }


_enhanced_calibrator: Optional[EnhancedCalibrator] = None


def get_enhanced_calibrator() -> EnhancedCalibrator:
    global _enhanced_calibrator
    if _enhanced_calibrator is None:
        _enhanced_calibrator = EnhancedCalibrator()
    return _enhanced_calibrator


class Calibrator:
    """Fachada de compatibilidad para el sistema mejorado."""

    def __init__(self) -> None:
        self.enhanced = get_enhanced_calibrator()
        logger._print_log("info", r"[CALIBRATOR] Fachada de compatibilidad inicializada [file:calibrator.py, method:__init__, line:995]", "calibrator.py", "method", 980)

    def calibrate_applications(
        self,
        app_name: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        return self.enhanced.calibrate_applications(app_name, force=force)

    def calibrate_chrome_both_screens(self) -> Dict[str, Any]:
        return self.enhanced.calibrate_chrome_both_screens()

    def _build_setup_info(self) -> Dict[str, Any]:
        return self.enhanced._build_setup_info()

    def _verify_system(self) -> bool:
        return self.enhanced._verify_system()

    def _has_calibration_command(self, app_name: str) -> bool:
        return self.enhanced._has_calibration_command(app_name)

    def _open_app_on_monitor(self, app_name: str, monitor_num: int) -> bool:
        return self.enhanced._open_app_on_monitor(app_name, monitor_num)

    def _close_app(self, app_name: str) -> bool:
        return self.enhanced._close_app(app_name)


def calibrate_chrome_both_screens() -> Dict[str, Any]:
    """Función global legacy."""
    return Calibrator().calibrate_chrome_both_screens()
