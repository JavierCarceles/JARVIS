"""Registro centralizado de acciones para JARVIS.

Este módulo define el contrato canónico entre las capacidades ejecutables y el
sistema de planificación. Mantiene separadas:
- definición/registro de acciones,
- validación de parámetros,
- precondiciones y efectos declarativos/funcionales,
- ejecución de la capacidad real.

Las funciones y callbacks no se serializan; las reglas declarativas sí.
"""

from __future__ import annotations

import importlib
import inspect
import math
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, get_args, get_origin

from src.hands.planner.preconditions_effects_types import Condition, Effect
from src.memory.prediction import get_prediction_memory
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ActionType(Enum):
    APPLICATION = "application"
    SYSTEM = "system"
    NAVIGATION = "navigation"
    INTERACTION = "interaction"
    CALIBRATION = "calibration"


StateCondition = Union[Dict[str, Any], List[Any], Callable[[Any], bool], None]
SuccessChecker = Callable[..., bool]


def _serialize_rule(value: Any) -> Any:
    """Serializa condiciones/efectos sin intentar serializar callbacks."""
    if isinstance(value, Condition):
        return {
            "type": value.type.value,
            "key": value.key,
            "expected_value": _serialize_rule(value.expected_value),
            "description": value.description,
            "parameters": _serialize_rule(value.parameters),
            "function": "FUNCION_NO_SERIALIZABLE"
            if value.function is not None
            else None,
        }
    if isinstance(value, Effect):
        return {
            "type": value.type,
            "key": value.key,
            "value": _serialize_rule(value.value),
            "description": value.description,
            "parameters": _serialize_rule(value.parameters),
            "cumulative": value.cumulative,
            "function": "FUNCION_NO_SERIALIZABLE"
            if value.function is not None
            else None,
        }
    if callable(value):
        return "FUNCION_NO_SERIALIZABLE"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _serialize_rule(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_rule(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize_rule(asdict(value))
    return value


def _get_state_value(state: Any, key: str, default: Any = None) -> Any:
    """Obtiene un valor de un dict, objeto con ``get`` o atributo."""
    if state is None:
        return default
    if not key:
        return default
    if isinstance(state, dict):
        return state.get(key, default)

    getter = getattr(state, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            try:
                return getter(key)
            except Exception:
                pass

    return getattr(state, key, default)


def _condition_from_dict(condition: Dict[str, Any]) -> Optional[Condition]:
    """Convierte una condición dict al modelo canónico cuando aporta un tipo."""
    if "type" not in condition:
        return None

    raw_type = condition.get("type")
    try:
        from src.hands.planner.preconditions_effects_types import ConditionType

        if isinstance(raw_type, ConditionType):
            condition_type = raw_type
        else:
            raw = str(raw_type).strip()
            try:
                condition_type = ConditionType(raw.lower())
            except ValueError:
                condition_type = ConditionType[raw.upper()]
    except (ImportError, KeyError, ValueError):
        return None

    key = condition.get("key", condition.get("state"))
    expected = condition.get(
        "expected_value",
        condition.get("equals", condition.get("expected", condition.get("value"))),
    )
    function = condition.get("function")
    parameters = dict(condition.get("parameters") or {})

    return Condition(
        type=condition_type,
        key=key,
        expected_value=expected,
        function=function if callable(function) else None,
        description=condition.get("description", ""),
        parameters=parameters,
    )


def _match_condition(state: Any, condition: Any) -> bool:
    """Evalúa una condición simple, compuesta, funcional u objeto Condition."""
    if isinstance(condition, Condition):
        try:
            return bool(
                condition.evaluate(
                    state if isinstance(state, dict) else dict(state or {})
                )
            )
        except Exception:
            return False

    if callable(condition):
        try:
            return bool(condition(state))
        except Exception:
            return False

    if isinstance(condition, str):
        return bool(_get_state_value(state, condition, False))

    if isinstance(condition, dict):
        # Forma compuesta declarativa: {conditions: [...], operator/op: and|or}
        if "conditions" in condition:
            operator = (
                str(condition.get("operator", condition.get("op", "and")))
                .strip()
                .lower()
            )
            children = condition.get("conditions") or []
            results = [_match_condition(state, child) for child in children]
            if operator == "or":
                return any(results)
            return all(results)

        # Forma canónica con ConditionType.
        condition_obj = _condition_from_dict(condition)
        if condition_obj is not None:
            try:
                return bool(
                    condition_obj.evaluate(
                        state if isinstance(state, dict) else dict(state or {})
                    )
                )
            except Exception:
                return False

        # Forma simple legacy: {key: value} o {state/key: ..., value/equals: ...}
        if "key" in condition or "state" in condition:
            key = condition.get("key", condition.get("state"))
            expected = condition.get(
                "equals",
                condition.get(
                    "value",
                    condition.get("expected", condition.get("expected_value", True)),
                ),
            )
            return _get_state_value(state, key, None) == expected

        return all(
            _get_state_value(state, key, None) == expected
            for key, expected in condition.items()
        )

    return bool(condition)


def _matches_conditions(state: Any, conditions: Any) -> bool:
    """Evalúa una colección de precondiciones con semántica AND por defecto."""
    if conditions is None or conditions == [] or conditions == {}:
        return True
    if isinstance(conditions, (list, tuple, set)):
        return all(_match_condition(state, condition) for condition in conditions)
    return _match_condition(state, conditions)


def _apply_effect_value(
    effect: Any,
    current_state: Dict[str, Any],
    execution_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Aplica un efecto mediante el modelo canónico o compatibilidad legacy."""
    state = dict(current_state)

    if isinstance(effect, Effect):
        updated = effect.apply(state, execution_result)
        if not isinstance(updated, dict):
            raise TypeError("Effect.apply debe devolver un dict de estado")
        return updated

    if callable(effect):
        try:
            updated = effect(state, execution_result)
        except TypeError:
            updated = effect(state)
        if not isinstance(updated, dict):
            raise TypeError("Un efecto funcional debe devolver un dict de estado")
        return updated

    if isinstance(effect, str):
        return Effect(type="state_set", key=effect, value=True).apply(
            state, execution_result
        )

    if isinstance(effect, dict):
        if callable(effect.get("function")):
            return _apply_effect_value(effect["function"], state, execution_result)
        effect_type = effect.get("type", "state_set")
        key = effect.get("key", effect.get("state"))
        if key is None and effect_type != "composite":
            return state
        effect_obj = Effect(
            type=effect_type,
            key=key,
            value=effect.get("value"),
            description=effect.get("description", ""),
            parameters=dict(effect.get("parameters") or {}),
            cumulative=bool(effect.get("cumulative", False)),
        )
        return effect_obj.apply(state, execution_result)

    raise TypeError(f"Efecto no soportado: {type(effect).__name__}")


@dataclass
class ActionInfo:
    """Metadatos y contrato ejecutable de una acción registrada."""

    name: str
    description: str
    action_type: ActionType
    function: Optional[Callable]
    parameters: Dict[str, Any]
    module: str
    category: str
    tags: List[str]
    confidence_threshold: float
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
    preconditions_functions: List[Callable] = field(default_factory=list)
    effects_functions: List[Callable] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.action_type, str):
            self.action_type = _resolve_action_type(self.action_type)
        self.parameters = dict(self.parameters or {})
        self.tags = list(self.tags or [])
        self.dependencies = list(self.dependencies or [])
        self.required_resources = list(self.required_resources or [])
        self.preconditions_functions = list(self.preconditions_functions or [])
        self.effects_functions = list(self.effects_functions or [])
        self.confidence_threshold = _normalize_confidence(self.confidence_threshold)
        self.cost = _normalize_cost(self.cost)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la acción a una estructura serializable."""
        return {
            "action": self.name,
            "description": self.description,
            "type": self.action_type.value,
            "category": self.category,
            "parameters": _serialize_rule(self.parameters),
            "module": self.module,
            "tags": list(self.tags),
            "confidence_threshold": self.confidence_threshold,
            "preconditions": _serialize_rule(self.preconditions),
            "effects": _serialize_rule(self.effects),
            "cost": self.cost,
            "dependencies": list(self.dependencies),
            "capability": self.capability,
            "application": self.application,
            "required_resources": list(self.required_resources),
            "requires_ui_element": self.requires_ui_element,
            "planner_enabled": self.planner_enabled,
            "preconditions_functions": "FUNCIONES_NO_SERIALIZABLES",
            "effects_functions": "FUNCIONES_NO_SERIALIZABLES",
        }

    def matches_preconditions(self, state: Any) -> bool:
        """Verifica todas las precondiciones declarativas y funcionales."""
        if not _matches_conditions(state, self.preconditions):
            return False

        for precond_func in self.preconditions_functions:
            if not callable(precond_func):
                logger._print_log("info", "Parámetro desconocido", "action_registry.py", "_validate_parameters", 679)
                return False
            try:
                if not bool(precond_func(state)):
                    return False
            except Exception as exc:
                logger._print_log("INFO", "Procesando solicitud", "action_registry.py", "matches_preconditions", 338)
                return False
        return True

    def verify_success(self, result: Any = None, *args: Any, **kwargs: Any) -> bool:
        """Ejecuta el verificador de éxito configurado, si existe."""
        if self.success_checker is None:
            return True
        try:
            return bool(self.success_checker(result, *args, **kwargs))
        except TypeError:
            try:
                return bool(self.success_checker(result))
            except Exception as exc:
                logger._print_log("INFO", "Procesando solicitud", "action_registry.py", "verify_success", 352)
                return False
        except Exception as exc:
            logger._print_log("INFO", "Procesando solicitud", "action_registry.py", "check_success", 355)
            return False

    def apply_effects(
        self,
        current_state: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aplica efectos declarativos y funcionales de manera acumulativa."""
        original_state = dict(current_state or {})
        state = dict(original_state)
        result = dict(execution_result or {})

        try:
            effects = [] if self.effects is None else self.effects
            if not isinstance(effects, (list, tuple, set)):
                effects = [effects]

            for effect in effects:
                state = _apply_effect_value(effect, state, result)

            for effect_func in self.effects_functions:
                if not callable(effect_func):
                    logger._print_log("info", "Parámetro requerido faltante", "action_registry.py", "_validate_parameters", 674)
                    continue
                try:
                    try:
                        updated_state = effect_func(state, result)
                    except TypeError:
                        updated_state = effect_func(state)
                    if not isinstance(updated_state, dict):
                        raise TypeError("El efecto funcional debe devolver un dict")
                    state = updated_state
                except Exception as exc:
                    logger._print_log("INFO", "Procesando solicitud", "action_registry.py", "apply_effects", 389)
                    return original_state

            return state
        except Exception as exc:
            logger._print_log("INFO", "Procesando solicitud", "action_registry.py", "_apply_effect_value", 394)
            return original_state


def _normalize_cost(cost: Any) -> float:
    try:
        normalized = float(cost)
    except (TypeError, ValueError):
        normalized = 1.0
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError("El coste de una acción debe ser finito y no negativo")
    return normalized


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.8
    if not math.isfinite(confidence):
        confidence = 0.8
    return max(0.0, min(1.0, confidence))


def _resolve_action_type(raw_type: Union[str, ActionType]) -> ActionType:
    if isinstance(raw_type, ActionType):
        return raw_type
    normalized = str(raw_type).strip().lower()
    for action_type in ActionType:
        if action_type.value == normalized or action_type.name.lower() == normalized:
            return action_type
    raise ValueError(f"ActionType desconocido: {raw_type}")


class ActionRegistry:
    """Registro y acceso a todas las acciones/capacidades disponibles."""

    def __init__(self) -> None:
        self.actions: Dict[str, ActionInfo] = {}
        self.categories: Dict[str, List[str]] = {}
        self._registered_modules: set[str] = set()
        self._action_count: int = 0
        self._execution_count: int = 0
        self._error_count: int = 0
        logger._print_log("info", "[ACTION-REGISTRY] Sistema de registro de acciones optimizado inicializado", "action_registry.py", "__init__", 450)

    @staticmethod
    def _extract_parameters(func: Callable) -> Dict[str, Any]:
        """Extrae metadatos básicos de parámetros de una función."""
        sig = inspect.signature(func)
        extracted: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self" or param.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue

            annotation = param.annotation
            if annotation is inspect.Parameter.empty:
                parameter_type: Any = "any"
            else:
                origin = get_origin(annotation)
                parameter_type = (
                    str(annotation)
                    if origin is not None
                    else (
                        annotation.__name__
                        if hasattr(annotation, "__name__")
                        else str(annotation)
                    )
                )

            extracted[param_name] = {
                "type": parameter_type,
                "default": (
                    param.default
                    if param.default is not inspect.Parameter.empty
                    else None
                ),
                "required": param.default is inspect.Parameter.empty,
            }

        return extracted

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
        preconditions_functions: Optional[List[Callable]] = None,
        effects_functions: Optional[List[Callable]] = None,
    ) -> Callable:
        """Devuelve un decorador que registra una función como acción."""

        normalized_action_type = _resolve_action_type(action_type)
        normalized_cost = _normalize_cost(cost)
        normalized_confidence = _normalize_confidence(confidence_threshold)

        def decorator(func: Callable) -> Callable:
            if not callable(func):
                raise TypeError(
                    f"La acción {name} debe asociarse a una función invocable"
                )

            action_parameters = (
                self._extract_parameters(func)
                if parameters is None
                else dict(parameters)
            )

            action_info = ActionInfo(
                name=name,
                description=description,
                action_type=normalized_action_type,
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
                planner_enabled=bool(planner_enabled),
                preconditions_functions=list(preconditions_functions or []),
                effects_functions=list(effects_functions or []),
            )

            setattr(func, "_jarvis_action_info", action_info)
            self._store_action_info(action_info)
            logger._print_log("info", "Procesando solicitud", "action_registry.py", "method", 332)
            return func

        return decorator

    def register_module(self, module_path: str) -> None:
        """Importa un módulo y registra sus acciones decoradas con logging optimizado."""
        if module_path in self._registered_modules:
            logger._print_log("debug", f"[ACTION-REGISTRY] Módulo ya registrado: {module_path}", "action_registry.py", "register_module", 548)
            return

        try:
            module = importlib.import_module(module_path)
            count = 0
            for _, obj in inspect.getmembers(module):
                action_info = getattr(obj, "_jarvis_action_info", None)
                if not isinstance(action_info, ActionInfo):
                    continue
                self._store_action_info(action_info)
                count += 1

            self._registered_modules.add(module_path)
            # Logging optimizado - solo información relevante
            if count > 0:
                logger._print_log("info", f"[ACTION-REGISTRY] Módulo {module_path}: {count} acciones registradas exitosamente", "action_registry.py", "register_module", 566)
            else:
                logger._print_log("debug", f"[ACTION-REGISTRY] Módulo {module_path}: no se encontraron acciones", "action_registry.py", "register_module", 568)
        except ImportError as exc:
            logger._print_log("warning", f"[ACTION-REGISTRY] Error al importar módulo {module_path}: {exc}", "action_registry.py", "register_module", 570)
        except Exception as exc:
            logger._print_log("error", f"[ACTION-REGISTRY] Error crítico al registrar módulo {module_path}: {exc}", "action_registry.py", "register_module", 572)

    def _store_action_info(self, action_info: ActionInfo) -> None:
        """Almacena ActionInfo manteniendo las categorías consistentes con logging optimizado."""
        previous = self.actions.get(action_info.name)
        if previous is not None and previous.category != action_info.category:
            previous_names = self.categories.get(previous.category, [])
            if action_info.name in previous_names:
                previous_names.remove(action_info.name)

        self.actions[action_info.name] = action_info
        category_actions = self.categories.setdefault(action_info.category, [])
        if action_info.name not in category_actions:
            category_actions.append(action_info.name)
            
        # Logging optimizado - solo registrar cuando sea relevante
        self._action_count += 1
        if self._action_count % 10 == 0:  # Log cada 10 acciones para evitar spam
            logger._print_log("info", f"[ACTION-REGISTRY] Registradas {self._action_count} acciones. Categoría: {action_info.category}", "action_registry.py", "_store_action_info", 584)

    def get_action(self, name: str) -> Optional[ActionInfo]:
        return self.actions.get(name)

    def get_actions_by_category(self, category: str) -> List[ActionInfo]:
        return [
            self.actions[name]
            for name in self.categories.get(category, [])
            if name in self.actions
        ]

    def get_all_actions(self) -> Dict[str, ActionInfo]:
        return self.actions.copy()

    def get_plannable_actions(self) -> Dict[str, ActionInfo]:
        return {
            name: info for name, info in self.actions.items() if info.planner_enabled
        }

    def get_actions_for_planner(self) -> List[Dict[str, Any]]:
        return [
            info.to_dict() for info in self.actions.values() if info.planner_enabled
        ]

    def get_actions_for_llama(self) -> List[Dict[str, Any]]:
        actions_list = [info.to_dict() for info in self.actions.values()]
        # Logging optimizado - solo información relevante
        if len(actions_list) > 0:
            logger._print_log("info", f"[ACTION-REGISTRY] Enviando {len(actions_list)} acciones al planificador", "action_registry.py", "get_actions_for_llama", 641)
        else:
            logger._print_log("warning", "[ACTION-REGISTRY] No hay acciones disponibles para el planificador", "action_registry.py", "get_actions_for_llama", 643)
        return actions_list

    @staticmethod
    def _validate_value_type(value: Any, expected_type: Any) -> bool:
        """Valida tipos básicos y anotaciones parametrizadas frecuentes."""
        if expected_type in (None, "any", "Any"):
            return True

        if isinstance(expected_type, str):
            type_name = expected_type.lower().strip()
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
                # Anotaciones string no resueltas se consideran compatibles.
                return True
            return isinstance(value, expected) and not (
                expected is int and isinstance(value, bool)
            )

        origin = get_origin(expected_type)
        args = get_args(expected_type)
        if origin is Union:
            return any(ActionRegistry._validate_value_type(value, arg) for arg in args)
        if origin in (list, List):
            if not isinstance(value, list):
                return False
            return not args or all(
                ActionRegistry._validate_value_type(item, args[0]) for item in value
            )
        if origin in (dict, Dict):
            return isinstance(value, dict)
        if isinstance(expected_type, type):
            if expected_type is int:
                return isinstance(value, int) and not isinstance(value, bool)
            return isinstance(value, expected_type)

        return True

    def validate_action(
        self, action_name: str, parameters: Optional[Dict[str, Any]]
    ) -> bool:
        """Valida presencia, nombres y tipos de los parámetros de la acción con logging optimizado."""
        action_info = self.get_action(action_name)
        if action_info is None:
            logger._print_log("error", f"[ACTION-REGISTRY] Acción no encontrada: {action_name}", "action_registry.py", "validate_action", 659)
            return False

        safe_parameters = dict(parameters or {})
        definitions = action_info.parameters or {}

        # Validar parámetros requeridos
        missing_required = []
        for param_name, param_info in definitions.items():
            info = param_info if isinstance(param_info, dict) else {}
            if info.get("required", False) and param_name not in safe_parameters:
                missing_required.append(param_name)

        if missing_required:
            logger._print_log("warning", f"[ACTION-REGISTRY] Parámetros requeridos faltantes para {action_name}: {missing_required}", "action_registry.py", "validate_action", 671)
            return False

        # Validar parámetros desconocidos
        unknown_params = []
        for param_name in safe_parameters:
            if param_name not in definitions:
                unknown_params.append(param_name)

        if unknown_params:
            logger._print_log("warning", f"[ACTION-REGISTRY] Parámetros desconocidos para {action_name}: {unknown_params}", "action_registry.py", "validate_action", 680)
            return False

        # Validar tipos de parámetros
        type_errors = []
        for param_name, value in safe_parameters.items():
            info = definitions.get(param_name, {})
            expected_type = info.get("type", "any") if isinstance(info, dict) else "any"
            if not self._validate_value_type(value, expected_type):
                type_errors.append(f"{param_name}: {type(value)} (esperado: {expected_type})")

        if type_errors:
            logger._print_log("warning", f"[ACTION-REGISTRY] Errores de tipo en {action_name}: {type_errors}", "action_registry.py", "validate_action", 692)
            return False

        logger._print_log("debug", f"[ACTION-REGISTRY] Validación exitosa para {action_name}", "action_registry.py", "validate_action", 695)
        return True

    def can_execute(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
        check_preconditions: bool = True,
    ) -> bool:
        """Determina si una acción está disponible en el estado proporcionado con logging optimizado."""
        action_info = self.get_action(action_name)
        if action_info is None:
            logger._print_log("debug", f"[ACTION-REGISTRY] Acción no disponible: {action_name} (no encontrada)", "action_registry.py", "can_execute", 691)
            return False

        safe_parameters = dict(parameters or {})
        if not self.validate_action(action_name, safe_parameters):
            logger._print_log("debug", f"[ACTION-REGISTRY] Acción {action_name} no disponible: validación fallida", "action_registry.py", "can_execute", 696)
            return False

        if check_preconditions and state is not None:
            preconditions_met = action_info.matches_preconditions(state)
            if not preconditions_met:
                logger._print_log("debug", f"[ACTION-REGISTRY] Acción {action_name} no disponible: precondiciones no cumplidas", "action_registry.py", "can_execute", 702)
            else:
                logger._print_log("debug", f"[ACTION-REGISTRY] Acción {action_name} disponible: precondiciones cumplidas", "action_registry.py", "can_execute", 704)
            return preconditions_met
        else:
            logger._print_log("debug", f"[ACTION-REGISTRY] Acción {action_name} disponible (sin verificación de precondiciones)", "action_registry.py", "can_execute", 707)
            return True

    def get_action_cost(self, action_name: str) -> float:
        action_info = self.get_action(action_name)
        if action_info is None:
            raise ValueError(f"Acción no encontrada: {action_name}")
        return action_info.cost

    def execute_action(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Ejecuta la capacidad real registrada con logging optimizado.

        La actualización del World State se mantiene fuera del registro; los
        efectos declarados se pueden aplicar después mediante ``ActionInfo.apply_effects``.
        """
        self._execution_count += 1
        
        # Logging optimizado - inicio de ejecución
        logger._print_log("info", f"[ACTION-REGISTRY] Ejecutando acción: {action_name} (ejecución #{self._execution_count})", "action_registry.py", "execute_action", 717)
        
        action_info = self.get_action(action_name)
        if not action_info:
            error_msg = f"Acción no encontrada: {action_name}"
            logger._print_log("error", f"[ACTION-REGISTRY] {error_msg}", "action_registry.py", "execute_action", 720)
            raise ValueError(error_msg)
        if action_info.function is None:
            error_msg = f"La acción no tiene función ejecutable: {action_name}"
            logger._print_log("error", f"[ACTION-REGISTRY] {error_msg}", "action_registry.py", "execute_action", 723)
            raise ValueError(error_msg)

        safe_parameters = dict(parameters or {})
        if not self.validate_action(action_name, safe_parameters):
            error_msg = f"Parámetros inválidos para la acción: {action_name}"
            logger._print_log("warning", f"[ACTION-REGISTRY] {error_msg}. Parámetros: {safe_parameters}", "action_registry.py", "execute_action", 727)
            raise ValueError(error_msg)

        try:
            prediction_memory = get_prediction_memory()
        except Exception:
            prediction_memory = None
            
        try:
            # Logging optimizado - parámetros validados
            logger._print_log("debug", f"[ACTION-REGISTRY] Acción {action_name}: parámetros validados, ejecutando función", "action_registry.py", "execute_action", 733)
            result = action_info.function(**safe_parameters)
            
            # Logging optimizado - ejecución exitosa
            logger._print_log("info", f"[ACTION-REGISTRY] Acción {action_name} ejecutada exitosamente", "action_registry.py", "execute_action", 736)
            
            try:
                if prediction_memory:
                    prediction_memory.record_command(
                        command=action_name,
                        success=True,
                        source="action_registry",
                    )
            except Exception as memory_error:
                logger._print_log("warning", f"[ACTION-REGISTRY] Error al registrar comando en memoria predictiva: {memory_error}", "action_registry.py", "execute_action", 745)
            return result
        except Exception as exc:
            # Logging optimizado - error detallado
            self._error_count += 1
            logger._print_log("error", f"[ACTION-REGISTRY] Error al ejecutar acción {action_name} (error #{self._error_count}): {exc}", "action_registry.py", "execute_action", 751)
            try:
                if prediction_memory:
                    prediction_memory.record_command(
                        command=action_name,
                        success=False,
                        source="action_registry",
                    )
            except Exception as memory_error:
                logger._print_log("warning", f"[ACTION-REGISTRY] Error al registrar comando fallido en memoria predictiva: {memory_error}", "action_registry.py", "execute_action", 759)
            raise

    def list_actions(self, category: Optional[str] = None) -> List[str]:
        if category:
            return [
                name
                for name in self.categories.get(category, [])
                if name in self.actions
            ]
        return list(self.actions.keys())

    def get_action_categories(self) -> List[str]:
        return list(self.categories.keys())
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema de registro de acciones para monitoreo y optimización."""
        stats = {
            "total_actions": len(self.actions),
            "total_categories": len(self.categories),
            "total_registrations": self._action_count,
            "total_executions": self._execution_count,
            "total_errors": self._error_count,
            "categories": list(self.categories.keys()),
            "actions_by_category": {cat: len(actions) for cat, actions in self.categories.items()},
            "plannable_actions": len([a for a in self.actions.values() if a.planner_enabled]),
            "average_cost": sum(a.cost for a in self.actions.values()) / len(self.actions) if self.actions else 0,
            "success_rate": (self._execution_count - self._error_count) / max(self._execution_count, 1) * 100,
            "last_registered": max((a for a in self.actions.values()), key=lambda x: getattr(x, '_registered_at', 0), default=None)
        }
        
        # Logging de estadísticas solo cuando sea relevante
        if self._execution_count % 50 == 0:  # Cada 50 ejecuciones
            logger._print_log("info", f"[ACTION-REGISTRY] Estadísticas: {stats['total_actions']} acciones, {stats['success_rate']:.1f}% tasa de éxito", "action_registry.py", "get_optimization_stats", 786)
            
        return stats
    
    def optimize_logging(self) -> None:
        """Optimiza el sistema de logging eliminando mensajes redundantes y mejorando la información."""
        # Aquí se podrían implementar estrategias de logging más avanzadas
        # como batching, niveles dinámicos, etc.
        logger._print_log("info", "[ACTION-REGISTRY] Sistema de logging optimizado", "action_registry.py", "optimize_logging", 794)


_action_registry: Optional[ActionRegistry] = None


def get_action_registry() -> ActionRegistry:
    global _action_registry
    if _action_registry is None:
        _action_registry = ActionRegistry()
    return _action_registry


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
    preconditions_functions: Optional[List[Callable]] = None,
    effects_functions: Optional[List[Callable]] = None,
) -> Callable:
    """Decorador de conveniencia para registrar una acción en el singleton."""
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
        preconditions_functions=preconditions_functions,
        effects_functions=effects_functions,
    )


def register_module(module_path: str) -> None:
    get_action_registry().register_module(module_path)


__all__ = [
    "ActionType",
    "ActionInfo",
    "ActionRegistry",
    "StateCondition",
    "SuccessChecker",
    "get_action_registry",
    "register_action",
    "register_module",
]
