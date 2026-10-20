"""
Registro unificado de acciones para Jarvis - VERSIÓN INTEGRADA.

Implementa un sistema de registro mediante decoradores que combina:
- Registro básico de acciones (compatibilidad legacy)
- Metadatos avanzados para planificación (nueva arquitectura)
- Validación y ejecución unificadas

Este archivo reemplaza la duplicidad entre:
- tools/registry.py (versión simple)
- hands/action_registry.py (versión completa)
"""

from __future__ import annotations

import importlib
import inspect
from src.utils.logger import get_logger
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, get_origin


logger = get_logger(__name__)


class ActionType(Enum):
    """Tipos de acciones disponibles."""

    APPLICATION = "application"
    SYSTEM = "system"
    NAVIGATION = "navigation"
    INTERACTION = "interaction"
    CALIBRATION = "calibration"


StateCondition = Union[Dict[str, Any], List[Any], Callable[[Any], bool], None]
SuccessChecker = Callable[..., bool]


# ============================================================================
# FUNCIONES HELPER PARA MANEJO DE ESTADO (PRECONDICIONES/EFECTOS)
# ============================================================================


def _get_state_value(state: Any, key: str, default: Any = None) -> Any:
    """Obtiene un valor de estado desde dicts u objetos con atributos/get."""

    if state is None:
        return default

    if isinstance(state, dict):
        return state.get(key, default)

    getter = getattr(state, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            pass

    return getattr(state, key, default)


def _match_condition(state: Any, condition: Any) -> bool:
    """Comprueba una única condición de estado."""

    if callable(condition):
        try:
            return bool(condition(state))
        except Exception:
            return False

    if isinstance(condition, str):
        return bool(_get_state_value(state, condition, False))

    if isinstance(condition, dict):
        if "key" in condition:
            key = condition["key"]
            expected = condition.get(
                "equals",
                condition.get("value", condition.get("expected", True)),
            )
            actual = _get_state_value(state, key, None)
            return actual == expected

        if "state" in condition:
            key = condition["state"]
            expected = condition.get(
                "equals",
                condition.get("value", condition.get("expected", True)),
            )
            actual = _get_state_value(state, key, None)
            return actual == expected

        for key, expected in condition.items():
            actual = _get_state_value(state, key, None)
            if actual != expected:
                return False

        return True

    return bool(condition)


def _matches_conditions(state: Any, conditions: Any) -> bool:
    """Comprueba un conjunto de condiciones de estado."""

    if conditions in (None, [], {}):
        return True

    if callable(conditions):
        return _match_condition(state, conditions)

    if isinstance(conditions, dict):
        return _match_condition(state, conditions)

    if isinstance(conditions, (list, tuple, set)):
        return all(_match_condition(state, condition) for condition in conditions)

    return _match_condition(state, conditions)


@dataclass
class ActionInfo:
    """Metadatos completos de una acción ejecutable y planificable."""

    name: str
    description: str
    action_type: ActionType
    function: Callable
    parameters: Dict[str, Any]
    module: str
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    confidence_threshold: float = 0.8
    preconditions: Any = field(default_factory=list)
    effects: Any = field(default_factory=list)
    cost: float = 1.0
    dependencies: List[str] = field(default_factory=list)
    capability: Optional[str] = None
    application: Optional[str] = None
    required_resources: List[str] = field(default_factory=list)
    requires_ui_element: Optional[str] = None
    success_checker: Optional[SuccessChecker] = None
    planner_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve una representación serializable de los metadatos."""
        return {
            "action": self.name,
            "description": self.description,
            "type": self.action_type.value,
            "category": self.category,
            "parameters": self.parameters,
            "module": self.module,
            "tags": list(self.tags),
            "confidence_threshold": self.confidence_threshold,
            "preconditions": self.preconditions,
            "effects": self.effects,
            "cost": self.cost,
            "dependencies": list(self.dependencies),
            "capability": self.capability,
            "application": self.application,
            "required_resources": list(self.required_resources),
            "requires_ui_element": self.requires_ui_element,
            "planner_enabled": self.planner_enabled,
        }

    def matches_preconditions(self, state: Any) -> bool:
        """Comprueba las precondiciones de la acción contra un estado."""
        return _matches_conditions(state, self.preconditions)

    def verify_success(self, result: Any = None, *args: Any, **kwargs: Any) -> bool:
        """Comprueba el éxito de la acción mediante su verificador opcional."""
        if self.success_checker is None:
            return True

        try:
            return bool(self.success_checker(result, *args, **kwargs))
        except TypeError:
            return bool(self.success_checker(result))
        except Exception as exc:
            logger.warning(
                "[ACTION-REGISTRY] Error verificando éxito de %s: %s",
                self.name,
                exc,
            )
            return False


class ActionRegistry:
    """
    Registro unificado de acciones para Jarvis.

    Combina compatibilidad legacy con metadatos avanzados para planificación.
    Es la fuente única de verdad para las acciones del sistema.
    """

    def __init__(self) -> None:
        """Inicializa el registro de acciones."""
        self.actions: Dict[str, ActionInfo] = {}
        self.categories: Dict[str, List[str]] = {}
        self.action_types: Dict[ActionType, List[str]] = {
            ActionType.APPLICATION: [],
            ActionType.SYSTEM: [],
            ActionType.NAVIGATION: [],
            ActionType.INTERACTION: [],
            ActionType.CALIBRATION: [],
        }
        self._registered_modules: set = set()

        logger.info(
            "[ACTION-REGISTRY] Sistema de registro de acciones inicializado (versión integrada)"
        )

    # ======================================================================
    # REGISTRO
    # ======================================================================

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normaliza el nombre de una acción."""
        return str(name).strip()

    @staticmethod
    def _normalize_description(description: str) -> str:
        """Normaliza la descripción de una acción."""
        return str(description).strip()

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        """
        Normaliza el umbral de confianza al rango [0.0, 1.0].

        Se mantiene como float para que el valor entregado al LLM sea
        consistente aunque el registro reciba un entero/string numérico.
        """
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.8

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _normalize_action_type(action_type: Any) -> ActionType:
        """
        Convierte un ActionType o su valor textual a ActionType.

        Esto mantiene compatibilidad con llamadas existentes que puedan
        proporcionar "system", "application", etc.
        """
        if isinstance(action_type, ActionType):
            return action_type

        try:
            return ActionType(str(action_type).strip().lower())
        except ValueError as exc:
            raise ValueError(f"Tipo de acción no válido: {action_type!r}") from exc

    @staticmethod
    def _extract_parameters(func: Callable) -> Dict[str, Any]:
        """Extrae un esquema básico de parámetros desde la firma de una función."""
        sig = inspect.signature(func)
        extracted_parameters: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            annotation = param.annotation

            if annotation == inspect.Parameter.empty:
                parameter_type = "any"
            else:
                origin = get_origin(annotation)

                if origin is not None:
                    parameter_type = str(annotation)
                elif hasattr(annotation, "__name__"):
                    parameter_type = annotation.__name__
                else:
                    parameter_type = str(annotation)

            extracted_parameters[param_name] = {
                "type": parameter_type,
                "default": (
                    param.default if param.default != inspect.Parameter.empty else None
                ),
                "required": param.default == inspect.Parameter.empty,
            }

        return extracted_parameters

    def register_action(
        self,
        name: str,
        description: str,
        action_type: ActionType = ActionType.APPLICATION,
        category: str = "general",
        tags: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        confidence_threshold: float = 0.8,
        preconditions: Any = None,
        effects: Any = None,
        cost: float = 1.0,
        dependencies: Optional[List[str]] = None,
        capability: Optional[str] = None,
        application: Optional[str] = None,
        required_resources: Optional[List[str]] = None,
        requires_ui_element: Optional[str] = None,
        success_checker: Optional[SuccessChecker] = None,
        planner_enabled: bool = True,
    ) -> Callable:
        """
        Decorador para registrar una acción.

        Args:
            name: Nombre único de la acción.
            description: Descripción clara de la acción.
            action_type: Tipo de acción.
            parameters: Parámetros esperados por la acción.
            confidence_threshold: Umbral de confianza entre 0 y 1.

        Returns:
            Decorador que registra la función y devuelve la misma función.
        """
        action_name = self._normalize_name(name)
        action_description = self._normalize_description(description)
        normalized_type = self._normalize_action_type(action_type)
        normalized_parameters = dict(parameters) if isinstance(parameters, dict) else {}
        normalized_confidence = self._normalize_confidence(confidence_threshold)

        if not action_name:
            raise ValueError("El nombre de la acción no puede estar vacío.")

        def decorator(func: Callable) -> Callable:
            if not callable(func):
                raise TypeError("register_action debe decorar una función invocable.")

            # Extraer parámetros si no se proporcionan
            action_parameters = (
                self._extract_parameters(func)
                if parameters is None
                else parameters.copy()
            )

            # Validar coste
            normalized_cost = float(cost)
            if normalized_cost < 0:
                raise ValueError(
                    f"El coste de una acción no puede ser negativo: {name}"
                )

            # Si el mismo nombre ya estaba registrado, eliminamos su entrada
            # anterior de la lista de tipos para evitar duplicados.
            previous = self.actions.get(action_name)

            if previous is not None:
                # Eliminar de categorías anteriores
                if previous.category in self.categories:
                    previous_names = self.categories[previous.category]
                    if action_name in previous_names:
                        previous_names.remove(action_name)

                # Eliminar de tipos anteriores
                previous_names = self.action_types.get(
                    previous.action_type,
                    [],
                )
                if action_name in previous_names:
                    previous_names.remove(action_name)

                logger.warning(
                    "[ACTION-REGISTRY] Acción reemplazada: %s",
                    action_name,
                )

            action_info = ActionInfo(
                name=action_name,
                description=action_description,
                action_type=normalized_type,
                function=func,
                parameters=action_parameters,
                module=func.__module__,
                category=category,
                tags=list(tags or []),
                confidence_threshold=normalized_confidence,
                preconditions=[] if preconditions is None else preconditions,
                effects=[] if effects is None else effects,
                cost=normalized_cost,
                dependencies=list(dependencies or []),
                capability=capability,
                application=application,
                required_resources=list(required_resources or []),
                requires_ui_element=requires_ui_element,
                success_checker=success_checker,
                planner_enabled=planner_enabled,
            )

            # Almacenar acción
            self.actions[action_name] = action_info

            # Indexar por categoría
            if category not in self.categories:
                self.categories[category] = []
            if action_name not in self.categories[category]:
                self.categories[category].append(action_name)

            # Indexar por tipo
            names_for_type = self.action_types.setdefault(
                normalized_type,
                [],
            )
            if action_name not in names_for_type:
                names_for_type.append(action_name)

            logger.info(
                "[ACTION-REGISTRY] Acción registrada: %s (%s | %s)",
                action_name,
                normalized_type.value,
                category,
            )

            return func

        return decorator

    # ======================================================================
    # CONSULTA
    # ======================================================================

    def get_action(
        self,
        name: str,
    ) -> Optional[ActionInfo]:
        """
        Obtiene información de una acción por nombre.

        Args:
            name: Nombre de la acción.

        Returns:
            ActionInfo o None si no existe.
        """
        action_name = self._normalize_name(name)
        return self.actions.get(action_name)

    def get_available_actions(
        self,
        action_type: Optional[ActionType] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene acciones disponibles en formato para el LLM.
        Mantiene compatibilidad con el formato legacy.

        Args:
            action_type: Filtra por tipo de acción cuando se especifica.

        Returns:
            Lista de diccionarios describiendo las acciones.
        """
        if action_type is not None:
            normalized_type = self._normalize_action_type(action_type)
            action_names = list(self.action_types.get(normalized_type, []))
        else:
            action_names = list(self.actions.keys())

        actions_list: List[Dict[str, Any]] = []

        for name in action_names:
            action_info = self.actions.get(name)

            if action_info is None:
                continue

            # Formato legacy (compatibilidad)
            actions_list.append(
                {
                    "name": action_info.name,
                    "description": action_info.description,
                    "type": action_info.action_type.value,
                    "parameters": dict(action_info.parameters),
                    "module": action_info.module,
                    "confidence_threshold": action_info.confidence_threshold,
                }
            )

        return actions_list

    def get_actions_for_planner(self) -> List[Dict[str, Any]]:
        """
        Genera metadatos serializables de las acciones para el planificador.
        Formato avanzado con todos los metadatos de planificación.
        """
        return [
            action_info.to_dict()
            for action_info in self.actions.values()
            if action_info.planner_enabled
        ]

    def get_plannable_actions(self) -> Dict[str, ActionInfo]:
        """
        Obtiene las acciones habilitadas para la capa de planificación.
        """
        return {
            name: action_info
            for name, action_info in self.actions.items()
            if action_info.planner_enabled
        }

    def get_actions_by_category(self, category: str) -> List[ActionInfo]:
        """
        Obtiene todas las acciones de una categoría.
        """
        action_names = self.categories.get(category, [])
        return [self.actions[name] for name in action_names if name in self.actions]

    def list_all_actions(self) -> Dict[str, List[str]]:
        """
        Lista todas las acciones organizadas por tipo.
        """
        return {
            action_type.value: list(names)
            for action_type, names in self.action_types.items()
        }

    def get_action_names_by_type(
        self,
        action_type: ActionType,
    ) -> List[str]:
        """
        Obtiene nombres de acciones por tipo.

        Returns:
            Copia de la lista de nombres registrados para ese tipo.
        """
        normalized_type = self._normalize_action_type(action_type)
        return list(self.action_types.get(normalized_type, []))

    def register_module(self, module_path: str) -> None:
        """Registra todas las acciones decoradas de un módulo."""
        if module_path in self._registered_modules:
            logger.debug(
                "[ACTION-REGISTRY] Módulo ya registrado: %s",
                module_path,
            )
            return

        try:
            module = importlib.import_module(module_path)

            for _, obj in inspect.getmembers(module):
                if not hasattr(obj, "_jarvis_action_info"):
                    continue

                action_info = getattr(obj, "_jarvis_action_info")
                self._store_action_info(action_info)

                logger.info(
                    "[ACTION-REGISTRY] Acción de módulo registrada: %s",
                    action_info.name,
                )

            self._registered_modules.add(module_path)

            logger.info(
                "[ACTION-REGISTRY] Módulo registrado: %s",
                module_path,
            )

        except ImportError as exc:
            logger._print_log("info", "Procesando solicitud", "registry.py", "method", 574)

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "registry.py", "method", 574)

    def _store_action_info(self, action_info: ActionInfo) -> None:
        """Almacena una acción manteniendo sus índices internos."""
        previous = self.actions.get(action_info.name)
        if previous is not None and previous.category != action_info.category:
            previous_names = self.categories.get(previous.category, [])
            if action_info.name in previous_names:
                previous_names.remove(action_info.name)

        self.actions[action_info.name] = action_info

        category_actions = self.categories.setdefault(action_info.category, [])
        if action_info.name not in category_actions:
            category_actions.append(action_info.name)

    def get_action_suggestions(
        self,
        partial_name: str,
        limit: int = 5,
    ) -> List[str]:
        """
        Obtiene sugerencias de acciones a partir de un nombre parcial.

        Args:
            partial_name: Texto parcial del nombre.
            limit: Máximo de sugerencias.

        Returns:
            Lista de nombres coincidentes.
        """
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 5

        if limit == 0:
            return []

        partial_lower = self._normalize_name(partial_name).lower()

        if not partial_lower:
            return list(self.actions.keys())[:limit]

        suggestions: List[str] = []

        for name in self.actions:
            if partial_lower in name.lower():
                suggestions.append(name)

                if len(suggestions) >= limit:
                    break

        return suggestions

    # ======================================================================
    # EJECUCIÓN
    # ======================================================================

    # ======================================================================
    # VALIDACIÓN AVANZADA
    # ======================================================================

    @staticmethod
    def _validate_value_type(value: Any, expected_type: Any) -> bool:
        """Valida de forma segura un tipo de parámetro."""

        if expected_type in (None, "any", "Any"):
            return True

        if isinstance(expected_type, type):
            expected = expected_type
        else:
            type_name = str(expected_type).lower().strip()

            type_map = {
                "int": int,
                "integer": int,
                "float": float,
                "str": str,
                "string": str,
                "bool": bool,
                "boolean": bool,
                "list": list,
                "dict": dict,
            }

            expected = type_map.get(type_name)

            if expected is None:
                return True

        if expected is bool:
            return isinstance(value, bool)

        return isinstance(value, expected)

    def validate_action(
        self,
        action_name: str,
        parameters: Dict[str, Any],
    ) -> bool:
        """Valida si una acción y sus parámetros son válidos."""
        action_info = self.get_action(action_name)

        if not action_info:
            logger.warning(
                "[ACTION-REGISTRY] Acción no encontrada: %s",
                action_name,
            )
            return False

        parameters = parameters or {}

        for param_name, param_info in action_info.parameters.items():
            if param_info.get("required", False) and param_name not in parameters:
                logger.warning(
                    "[ACTION-REGISTRY] Parámetro requerido faltante: %s",
                    param_name,
                )
                return False

        for param_name in parameters:
            if param_name not in action_info.parameters:
                logger.warning(
                    "[ACTION-REGISTRY] Parámetro desconocido para %s: %s",
                    action_name,
                    param_name,
                )
                return False

        for param_name, value in parameters.items():
            param_info = action_info.parameters[param_name]
            expected_type = param_info.get("type", "any")

            if not self._validate_value_type(value, expected_type):
                logger.warning(
                    "[ACTION-REGISTRY] Tipo incorrecto para %s: esperado %s, recibido %s",
                    param_name,
                    expected_type,
                    type(value),
                )
                return False

        return True

    def can_execute(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
        check_preconditions: bool = True,
    ) -> bool:
        """
        Comprueba si una acción puede ejecutarse según parámetros y estado.

        La comprobación de estado es opcional para mantener compatibilidad con
        el flujo actual de ejecución directa.
        """
        action_info = self.get_action(action_name)
        if action_info is None:
            return False

        safe_parameters = parameters or {}

        if not self.validate_action(action_name, safe_parameters):
            return False

        if check_preconditions and state is not None:
            return action_info.matches_preconditions(state)

        return True

    def get_action_cost(self, action_name: str) -> float:
        """Obtiene el coste declarado de una acción."""
        action_info = self.get_action(action_name)
        if action_info is None:
            raise ValueError(f"Acción no encontrada: {action_name}")

        return action_info.cost

    # ======================================================================
    # EJECUCIÓN
    # ======================================================================

    def execute_action(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Ejecuta una acción registrada con parámetros nombrados.

        Se conserva como punto de compatibilidad para el sistema actual.
        La futura arquitectura puede hacer que Planner/Executor utilicen la misma
        información sin delegar la planificación al registro.
        """
        action_info = self.get_action(action_name)

        if not action_info:
            raise ValueError(f"Acción no encontrada: {action_name}")

        safe_parameters = parameters or {}

        if not self.validate_action(action_name, safe_parameters):
            raise ValueError(f"Parámetros inválidos para la acción: {action_name}")

        # Importar aquí para evitar dependencia circular
        try:
            from src.memory.prediction import get_prediction_memory

            prediction_memory = get_prediction_memory()
        except ImportError:
            prediction_memory = None

        try:
            result = action_info.function(**safe_parameters)

            logger.info(
                "[ACTION-REGISTRY] Acción ejecutada: %s",
                action_name,
            )

            if prediction_memory:
                try:
                    prediction_memory.record_command(
                        command=action_name,
                        success=True,
                        source="action_registry",
                    )
                except Exception as memory_error:
                    logger.warning(
                        "[ACTION-REGISTRY] No se pudo registrar el éxito en PredictionMemory: %s",
                        memory_error,
                    )

            return result

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "registry.py", "method", 574)

            if prediction_memory:
                try:
                    prediction_memory.record_command(
                        command=action_name,
                        success=False,
                        source="action_registry",
                    )
                except Exception as memory_error:
                    logger.warning(
                        "[ACTION-REGISTRY] No se pudo registrar el fallo en PredictionMemory: %s",
                        memory_error,
                    )

            raise

    def execute_action_legacy(
        self,
        name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Ejecuta una acción por su nombre (compatibilidad legacy).

        Args:
            name: Nombre de la acción.
            *args: Argumentos posicionales.
            **kwargs: Argumentos con nombre.

        Returns:
            Resultado de la función registrada.
        """
        action_name = self._normalize_name(name)
        action_info = self.get_action(action_name)

        if action_info is None:
            raise ValueError(f"Acción no encontrada: {action_name}")

        try:
            logger.info(
                "[ACTION-REGISTRY] Ejecutando acción (legacy): %s",
                action_name,
            )

            result = action_info.function(
                *args,
                **kwargs,
            )

            logger.info(
                "[ACTION-REGISTRY] Acción %s ejecutada exitosamente",
                action_name,
            )

            return result

        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "registry.py", "method", 574)
            raise

    # ======================================================================
    # VALIDACIÓN
    # ======================================================================

    def validate_parameters(
        self,
        name: str,
        parameters: Dict[str, Any],
    ) -> bool:
        """
        Valida los nombres de parámetros definidos por la acción.

        Esta validación comprueba únicamente:
        - que existan los parámetros marcados como required;
        - que no se envíen parámetros desconocidos.

        No intenta convertir valores ni deducir tipos que no estén
        especificados en los metadatos de la acción.
        """
        action_info = self.get_action(name)

        if action_info is None:
            logger.warning(
                "[ACTION-REGISTRY] Acción inexistente al validar: %s",
                name,
            )
            return False

        if not isinstance(parameters, dict):
            logger.warning(
                "[ACTION-REGISTRY] Los parámetros de %s no son un diccionario",
                name,
            )
            return False

        expected_params = set(action_info.parameters.keys())
        provided_params = set(parameters.keys())

        required_params = {
            param_name
            for param_name, config in action_info.parameters.items()
            if isinstance(config, dict) and bool(config.get("required", False))
        }

        missing_required = required_params - provided_params

        if missing_required:
            logger.warning(
                "[ACTION-REGISTRY] Parámetros requeridos faltantes para %s: %s",
                name,
                sorted(missing_required),
            )
            return False

        unexpected_params = provided_params - expected_params

        if unexpected_params:
            logger.warning(
                "[ACTION-REGISTRY] Parámetros no esperados para %s: %s",
                name,
                sorted(unexpected_params),
            )
            return False

        return True

    # ======================================================================
    # LIMPIEZA
    # ======================================================================

    def clear_actions(self) -> None:
        """Limpia todas las acciones registradas."""
        self.actions.clear()

        for action_type in self.action_types:
            self.action_types[action_type].clear()

        logger._print_log("info", "[ACTION-REGISTRY] Todas las acciones han sido limpiadas", "registry.py", "method", 955)


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================


_registry_instance: Optional[ActionRegistry] = None


def get_action_registry() -> ActionRegistry:
    """Obtiene la instancia global única del registro de acciones."""
    global _registry_instance

    if _registry_instance is None:
        _registry_instance = ActionRegistry()

    return _registry_instance


# ============================================================================
# ATAJOS GLOBALES
# ============================================================================


def register_action(
    name: str,
    description: str,
    action_type: ActionType = ActionType.APPLICATION,
    category: str = "general",
    tags: Optional[List[str]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    confidence_threshold: float = 0.8,
    preconditions: Any = None,
    effects: Any = None,
    cost: float = 1.0,
    dependencies: Optional[List[str]] = None,
    capability: Optional[str] = None,
    application: Optional[str] = None,
    required_resources: Optional[List[str]] = None,
    requires_ui_element: Optional[str] = None,
    success_checker: Optional[SuccessChecker] = None,
    planner_enabled: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Atajo para registrar una acción usando la instancia global.
    Versión completa con todos los metadatos de planificación.

    Returns:
        Decorador de registro.
    """
    registry = get_action_registry()

    return registry.register_action(
        name=name,
        description=description,
        action_type=action_type,
        category=category,
        tags=tags,
        parameters=parameters,
        confidence_threshold=confidence_threshold,
        preconditions=preconditions,
        effects=effects,
        cost=cost,
        dependencies=dependencies,
        capability=capability,
        application=application,
        required_resources=required_resources,
        requires_ui_element=requires_ui_element,
        success_checker=success_checker,
        planner_enabled=planner_enabled,
    )


def register_action_legacy(
    name: str,
    description: str,
    action_type: ActionType = ActionType.SYSTEM,
    parameters: Optional[Dict[str, Any]] = None,
    confidence_threshold: float = 0.8,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Atajo para registrar una acción usando la instancia global.
    Versión legacy simplificada para compatibilidad.

    Returns:
        Decorador de registro.
    """
    registry = get_action_registry()

    return registry.register_action(
        name=name,
        description=description,
        action_type=action_type,
        parameters=parameters,
        confidence_threshold=confidence_threshold,
    )


def get_available_actions(
    action_type: Optional[ActionType] = None,
) -> List[Dict[str, Any]]:
    """
    Atajo para obtener las acciones disponibles desde el registro global.
    """
    registry = get_action_registry()
    return registry.get_available_actions(action_type)


def get_action(
    name: str,
) -> Optional[ActionInfo]:
    """
    Atajo para obtener una acción desde el registro global.
    """
    registry = get_action_registry()
    return registry.get_action(name)
