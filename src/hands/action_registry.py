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
import ast
import threading
import time
import types
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from src.hands.planner.preconditions_effects_types import Condition, Effect
from src.memory.prediction import get_prediction_memory
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _log(level: str, message: Any, *_context: Any) -> None:
    """Registra mensajes sin hacer que un logger incompatible rompa el registro."""
    normalized_level = str(level or "info").strip().lower()
    if normalized_level == "warn":
        normalized_level = "warning"
    method = getattr(logger, normalized_level, None)
    if not callable(method):
        method = getattr(logger, "info", None)
    try:
        if callable(method):
            method("%s", str(message))
            return
    except TypeError:
        try:
            method(str(message))
            return
        except Exception:
            pass
    except Exception:
        pass
    try:
        printer = getattr(logger, "_print_log", None)
        if callable(printer):
            printer(normalized_level, str(message), "action_registry.py", "_log", 0)
    except Exception:
        pass


def _safe_copy(value: Any) -> Any:
    """Copia defensivamente datos de estado preservando el fallback ante objetos opacos."""
    try:
        return deepcopy(value)
    except Exception:
        if isinstance(value, dict):
            copied = {}
            for key, item in value.items():
                try:
                    copied[key] = _safe_copy(item)
                except Exception:
                    copied[key] = item
            return copied
        if isinstance(value, list):
            return [_safe_copy(item) for item in value]
        if isinstance(value, tuple):
            return tuple(_safe_copy(item) for item in value)
        return value


def _as_list(value: Any) -> List[Any]:
    """Normaliza colecciones sin dividir por error cadenas en caracteres."""
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _state_to_dict(state: Any) -> Dict[str, Any]:
    """Normaliza estados dict, dataclass y objetos con ``to_dict`` sin mutarlos."""
    if isinstance(state, dict):
        return dict(state)
    if state is None:
        return {}
    to_dict = getattr(state, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
            if isinstance(converted, dict):
                return dict(converted)
        except Exception:
            pass
    try:
        values = vars(state)
        if isinstance(values, dict):
            return {
                key: value
                for key, value in values.items()
                if not str(key).startswith("_")
            }
    except (TypeError, AttributeError):
        pass
    return {}


def _invoke_compatible(function: Callable[..., Any], candidates: Any) -> Any:
    """Llama un callback con la primera firma compatible, sin repetir sus efectos."""
    candidate_list = list(candidates)
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        for args, kwargs in candidate_list:
            try:
                signature.bind(*args, **kwargs)
            except TypeError:
                continue
            return function(*args, **kwargs)
        raise TypeError(
            f"La firma de {function!r} no coincide con las llamadas admitidas"
        )

    last_error = None
    for args, kwargs in candidate_list:
        try:
            return function(*args, **kwargs)
        except TypeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise TypeError("No se proporcionaron firmas candidatas")


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
            "type": getattr(value.type, "value", value.type),
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
            "type": _serialize_rule(value.type),
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
    if isinstance(value, (list, tuple)):
        return [_serialize_rule(item) for item in value]
    if isinstance(value, set):
        return sorted((_serialize_rule(item) for item in value), key=repr)
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return _serialize_rule(asdict(value))
        except Exception:
            return repr(value)
    if isinstance(value, type):
        return value.__name__
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # Paths and similar scalar wrappers are usually safely representable as text.
    if hasattr(value, "__fspath__"):
        try:
            return str(value)
        except Exception:
            pass
    return repr(value)


def _get_state_value(state: Any, key: str, default: Any = None) -> Any:
    """Obtiene un valor de un dict, objeto con ``get`` o atributo."""
    if state is None:
        return default
    if not key:
        return default
    if isinstance(state, dict):
        if key in state:
            return state[key]
        current: Any = state
        for part in str(key).split("."):
            if not isinstance(current, dict) or part not in current:
                break
            current = current[part]
        else:
            return current
        return default

    getter = getattr(state, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            try:
                return getter(key)
            except Exception:
                pass

    if hasattr(state, key):
        return getattr(state, key, default)
    current = state
    for part in str(key).split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
        else:
            current = getattr(current, part, default)
            if current is default:
                return default
    return current


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
            return bool(condition.evaluate(_state_to_dict(state)))
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
            if operator not in {"and", "or"} or not isinstance(
                children, (list, tuple, set)
            ):
                return False
            results = [_match_condition(state, child) for child in children]
            if operator == "or":
                return any(results)
            return all(results)

        # Forma canónica con ConditionType.
        condition_obj = _condition_from_dict(condition)
        if condition_obj is not None:
            try:
                return bool(condition_obj.evaluate(_state_to_dict(state)))
            except Exception:
                return False
        if "type" in condition:
            # Un tipo declarado pero desconocido no debe degradarse a una
            # comparación legacy que pueda habilitar accidentalmente la acción.
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
    state = _safe_copy(dict(current_state))

    if isinstance(effect, Effect):
        updated = effect.apply(state, execution_result)
        if not isinstance(updated, dict):
            raise TypeError("Effect.apply debe devolver un dict de estado")
        return updated

    if callable(effect):
        updated = _invoke_compatible(
            effect,
            [((state, execution_result), {}), ((state,), {})],
        )
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
        effect_type = getattr(effect_type, "value", effect_type)
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
    _registered_at: float = field(default_factory=time.time, repr=False, compare=False)
    accepts_extra_parameters: bool = False

    def __post_init__(self) -> None:
        self.name = str(self.name or "").strip()
        if not self.name:
            raise ValueError("El nombre de la acción no puede estar vacío")
        if isinstance(self.action_type, str):
            self.action_type = _resolve_action_type(self.action_type)
        if not isinstance(self.action_type, ActionType):
            raise TypeError("action_type debe ser ActionType o una cadena válida")
        self.description = str(self.description or "")
        self.category = str(self.category or "general").strip() or "general"
        self.module = str(self.module or "")
        self.parameters = dict(self.parameters or {})
        self.tags = _as_list(self.tags)
        self.dependencies = _as_list(self.dependencies)
        self.required_resources = _as_list(self.required_resources)
        self.preconditions_functions = _as_list(self.preconditions_functions)
        self.effects_functions = _as_list(self.effects_functions)
        if callable(self.function):
            try:
                signature = inspect.signature(self.function)
                self.accepts_extra_parameters = bool(
                    self.accepts_extra_parameters
                    or any(
                        parameter.kind == inspect.Parameter.VAR_KEYWORD
                        for parameter in signature.parameters.values()
                    )
                )
            except (TypeError, ValueError):
                pass
        self.accepts_extra_parameters = bool(self.accepts_extra_parameters)
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
            "accepts_extra_parameters": self.accepts_extra_parameters,
            "preconditions_functions": "FUNCIONES_NO_SERIALIZABLES",
            "effects_functions": "FUNCIONES_NO_SERIALIZABLES",
        }

    def matches_preconditions(self, state: Any) -> bool:
        """Verifica todas las precondiciones declarativas y funcionales."""
        if not _matches_conditions(state, self.preconditions):
            return False

        for precond_func in self.preconditions_functions:
            if not callable(precond_func):
                _log(
                    "warning", f"Precondición no invocable configurada para {self.name}"
                )
                return False
            try:
                if not bool(precond_func(state)):
                    return False
            except Exception as exc:
                _log("warning", f"Falló una precondición de {self.name}: {exc}")
                return False
        return True

    def verify_success(self, result: Any = None, *args: Any, **kwargs: Any) -> bool:
        """Ejecuta el verificador de éxito configurado, si existe."""
        if self.success_checker is None:
            return True
        try:
            candidate_args = (result, *args)
            return bool(
                _invoke_compatible(
                    self.success_checker,
                    [(candidate_args, kwargs), ((result,), {}), ((), {})],
                )
            )
        except Exception as exc:
            _log("warning", f"El verificador de éxito de {self.name} falló: {exc}")
            return False

    def apply_effects(
        self,
        current_state: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aplica efectos declarativos y funcionales de manera transaccional."""
        if current_state is not None and not isinstance(current_state, dict):
            raise TypeError("current_state debe ser un diccionario")
        if execution_result is not None and not isinstance(execution_result, dict):
            raise TypeError("execution_result debe ser un diccionario")
        original_state = _safe_copy(dict(current_state or {}))
        state = _safe_copy(original_state)
        result = _safe_copy(dict(execution_result or {}))

        try:
            effects = [] if self.effects is None else self.effects
            if not isinstance(effects, (list, tuple, set)):
                effects = [effects]

            for effect in effects:
                state = _apply_effect_value(effect, state, result)

            for effect_func in self.effects_functions:
                if not callable(effect_func):
                    _log(
                        "warning",
                        f"Efecto no invocable configurado para {self.name}; se revierte el estado",
                    )
                    return original_state
                try:
                    updated_state = _invoke_compatible(
                        effect_func,
                        [((state, result), {}), ((state,), {})],
                    )
                    if not isinstance(updated_state, dict):
                        raise TypeError("El efecto funcional debe devolver un dict")
                    state = updated_state
                except Exception as exc:
                    _log("warning", f"Efecto funcional fallido en {self.name}: {exc}")
                    return original_state

            return state
        except Exception as exc:
            _log("warning", f"No se pudieron aplicar los efectos de {self.name}: {exc}")
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


def _split_type_arguments(value: str, separator: str = ",") -> List[str]:
    """Divide argumentos de tipo respetando corchetes anidados."""
    parts: List[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char in "[({":
            depth += 1
        elif char in "])}":
            depth = max(0, depth - 1)
        elif char == separator and depth == 0:
            part = value[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


class ActionRegistry:
    """Registro y acceso a todas las acciones/capacidades disponibles."""

    def __init__(self) -> None:
        self.actions: Dict[str, ActionInfo] = {}
        self.categories: Dict[str, List[str]] = {}
        self._registered_modules: set[str] = set()
        self._action_count: int = 0
        self._execution_count: int = 0
        self._error_count: int = 0
        self._lock = threading.RLock()
        _log("info", "[ACTION-REGISTRY] Sistema de registro de acciones inicializado")

    @staticmethod
    def _extract_parameters(func: Callable) -> Dict[str, Any]:
        """Extrae metadatos básicos de parámetros de una función."""
        sig = inspect.signature(func)
        try:
            resolved_hints = get_type_hints(func)
        except Exception:
            resolved_hints = {}
        extracted: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self" or param.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue

            annotation = resolved_hints.get(param_name, param.annotation)
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

        if not str(name or "").strip():
            raise ValueError("El nombre de la acción no puede estar vacío")
        if not str(category or "").strip():
            category = "general"
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
                tags=_as_list(tags),
                confidence_threshold=normalized_confidence,
                preconditions=[] if preconditions is None else preconditions,
                effects=[] if effects is None else effects,
                cost=normalized_cost,
                dependencies=_as_list(dependencies),
                capability=capability,
                application=application,
                required_resources=_as_list(required_resources),
                requires_ui_element=requires_ui_element,
                success_checker=success_checker,
                planner_enabled=bool(planner_enabled),
                preconditions_functions=_as_list(preconditions_functions),
                effects_functions=_as_list(effects_functions),
            )

            setattr(func, "_jarvis_action_info", action_info)
            self._store_action_info(action_info)
            return func

        return decorator

    def register_module(self, module_path: str) -> None:
        """Importa un módulo y registra sus acciones decoradas con logging optimizado."""
        if not isinstance(module_path, str) or not module_path.strip():
            raise ValueError("module_path debe ser una ruta de módulo no vacía")
        module_path = module_path.strip()
        with self._lock:
            if module_path in self._registered_modules:
                _log("debug", f"[ACTION-REGISTRY] Módulo ya registrado: {module_path}")
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

            with self._lock:
                self._registered_modules.add(module_path)
            # Logging optimizado - solo información relevante
            if count > 0:
                _log(
                    "info",
                    f"[ACTION-REGISTRY] Módulo {module_path}: {count} acciones registradas exitosamente",
                    "action_registry.py",
                    "register_module",
                    566,
                )
            else:
                _log(
                    "debug",
                    f"[ACTION-REGISTRY] Módulo {module_path}: no se encontraron acciones",
                    "action_registry.py",
                    "register_module",
                    568,
                )
        except ImportError as exc:
            _log(
                "warning",
                f"[ACTION-REGISTRY] Error al importar módulo {module_path}: {exc}",
                "action_registry.py",
                "register_module",
                570,
            )
        except Exception as exc:
            _log(
                "error",
                f"[ACTION-REGISTRY] Error crítico al registrar módulo {module_path}: {exc}",
                "action_registry.py",
                "register_module",
                572,
            )

    def _store_action_info(self, action_info: ActionInfo) -> None:
        """Almacena una acción y mantiene los índices de categorías sincronizados."""
        if not isinstance(action_info, ActionInfo):
            raise TypeError("action_info debe ser una instancia de ActionInfo")
        with self._lock:
            previous = self.actions.get(action_info.name)
            if previous is not None and previous.category != action_info.category:
                previous_names = self.categories.get(previous.category, [])
                if action_info.name in previous_names:
                    previous_names.remove(action_info.name)
                if not previous_names:
                    self.categories.pop(previous.category, None)

            self.actions[action_info.name] = action_info
            category_actions = self.categories.setdefault(action_info.category, [])
            if action_info.name not in category_actions:
                category_actions.append(action_info.name)

            self._action_count += 1
            if self._action_count % 10 == 0:
                _log(
                    "info",
                    f"[ACTION-REGISTRY] Registradas {self._action_count} acciones. "
                    f"Categoría: {action_info.category}",
                )

    def get_action(self, name: str) -> Optional[ActionInfo]:
        with self._lock:
            return self.actions.get(name)

    def get_actions_by_category(self, category: str) -> List[ActionInfo]:
        with self._lock:
            return [
                self.actions[name]
                for name in self.categories.get(category, [])
                if name in self.actions
            ]

    def get_all_actions(self) -> Dict[str, ActionInfo]:
        with self._lock:
            return self.actions.copy()

    def get_plannable_actions(self) -> Dict[str, ActionInfo]:
        with self._lock:
            return {
                name: info
                for name, info in self.actions.items()
                if info.planner_enabled
            }

    def get_actions_for_planner(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = [info for info in self.actions.values() if info.planner_enabled]
        return [info.to_dict() for info in items]

    def get_actions_for_llama(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self.actions.values())
        actions_list = [info.to_dict() for info in items]
        # Logging optimizado - solo información relevante
        if len(actions_list) > 0:
            _log(
                "info",
                f"[ACTION-REGISTRY] Enviando {len(actions_list)} acciones al planificador",
                "action_registry.py",
                "get_actions_for_llama",
                641,
            )
        else:
            _log(
                "warning",
                "[ACTION-REGISTRY] No hay acciones disponibles para el planificador",
                "action_registry.py",
                "get_actions_for_llama",
                643,
            )
        return actions_list

    @staticmethod
    def _validate_value_type(value: Any, expected_type: Any) -> bool:
        """Valida tipos Python y anotaciones comunes, incluidas las diferidas."""
        if expected_type in (None, "any", "Any", Any, inspect.Parameter.empty):
            return True

        if isinstance(expected_type, str):
            annotation = expected_type.strip().replace("typing.", "")
            lowered = annotation.lower()
            primitive_types = {
                "int": int,
                "integer": int,
                "float": float,
                "str": str,
                "string": str,
                "bool": bool,
                "boolean": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "bytes": bytes,
                "none": type(None),
                "nonetype": type(None),
                "any": Any,
            }
            if lowered in primitive_types:
                expected = primitive_types[lowered]
                if expected is Any:
                    return True
                if expected is float:
                    return isinstance(value, (int, float)) and not isinstance(
                        value, bool
                    )
                return isinstance(value, expected) and not (
                    expected is int and isinstance(value, bool)
                )

            # A small parser handles forward-reference strings without eval().
            if lowered.startswith("literal[") and annotation.endswith("]"):
                raw_literals = annotation[annotation.find("[") + 1 : -1]
                literal_values = []
                for part in _split_type_arguments(raw_literals):
                    try:
                        literal_values.append(ast.literal_eval(part))
                    except (ValueError, SyntaxError):
                        literal_values.append(part.strip().strip("\"'"))
                return value in literal_values
            if lowered.startswith("optional[") and annotation.endswith("]"):
                inner = annotation[annotation.find("[") + 1 : -1].strip()
                return value is None or ActionRegistry._validate_value_type(
                    value, inner
                )
            if lowered.startswith("union[") and annotation.endswith("]"):
                inner = annotation[annotation.find("[") + 1 : -1]
                return any(
                    ActionRegistry._validate_value_type(value, part)
                    for part in _split_type_arguments(inner)
                )
            if "|" in annotation:
                return any(
                    ActionRegistry._validate_value_type(value, part)
                    for part in _split_type_arguments(annotation, separator="|")
                )
            for container_name, container_type in (
                ("list", list),
                ("List", list),
                ("set", set),
                ("Set", set),
            ):
                prefix = container_name + "["
                if annotation.startswith(prefix) and annotation.endswith("]"):
                    if not isinstance(value, container_type):
                        return False
                    type_parts = _split_type_arguments(annotation[len(prefix) : -1])
                    return not type_parts or all(
                        ActionRegistry._validate_value_type(item, type_parts[0])
                        for item in value
                    )
            for container_name in ("tuple", "Tuple"):
                prefix = container_name + "["
                if annotation.startswith(prefix) and annotation.endswith("]"):
                    if not isinstance(value, tuple):
                        return False
                    type_parts = _split_type_arguments(annotation[len(prefix) : -1])
                    if not type_parts:
                        return True
                    if len(type_parts) == 2 and type_parts[1] == "...":
                        return all(
                            ActionRegistry._validate_value_type(item, type_parts[0])
                            for item in value
                        )
                    return len(value) == len(type_parts) and all(
                        ActionRegistry._validate_value_type(item, item_type)
                        for item, item_type in zip(value, type_parts)
                    )
            for container_name in ("dict", "Dict"):
                prefix = container_name + "["
                if annotation.startswith(prefix) and annotation.endswith("]"):
                    if not isinstance(value, dict):
                        return False
                    type_parts = _split_type_arguments(annotation[len(prefix) : -1])
                    if len(type_parts) >= 2:
                        return all(
                            ActionRegistry._validate_value_type(key, type_parts[0])
                            and ActionRegistry._validate_value_type(item, type_parts[1])
                            for key, item in value.items()
                        )
                    return True
            # Unresolved forward references stay permissive for compatibility.
            return True

        origin = get_origin(expected_type)
        args = get_args(expected_type)
        if origin is Literal:
            return value in args
        if origin in (Union, types.UnionType):
            return any(ActionRegistry._validate_value_type(value, arg) for arg in args)
        if origin in (list, List, set, tuple):
            if not isinstance(value, origin if isinstance(origin, type) else list):
                return False
            if not args:
                return True
            if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
                return all(
                    ActionRegistry._validate_value_type(item, args[0]) for item in value
                )
            if origin is tuple and len(args) > 1:
                return len(value) == len(args) and all(
                    ActionRegistry._validate_value_type(item, item_type)
                    for item, item_type in zip(value, args)
                )
            return all(
                ActionRegistry._validate_value_type(item, args[0]) for item in value
            )
        if origin in (dict, Dict):
            if not isinstance(value, dict):
                return False
            return not args or all(
                ActionRegistry._validate_value_type(key, args[0])
                and (
                    len(args) < 2 or ActionRegistry._validate_value_type(item, args[1])
                )
                for key, item in value.items()
            )
        if expected_type is type(None):
            return value is None
        if isinstance(expected_type, type):
            if expected_type is int:
                return isinstance(value, int) and not isinstance(value, bool)
            if expected_type is float:
                return isinstance(value, (int, float)) and not isinstance(value, bool)
            return isinstance(value, expected_type)
        try:
            return isinstance(value, expected_type)
        except TypeError:
            return True

    def validate_action(
        self, action_name: str, parameters: Optional[Dict[str, Any]]
    ) -> bool:
        """Valida presencia, nombres y tipos de los parámetros de la acción con logging optimizado."""
        action_info = self.get_action(action_name)
        if action_info is None:
            _log(
                "error",
                f"[ACTION-REGISTRY] Acción no encontrada: {action_name}",
                "action_registry.py",
                "validate_action",
                659,
            )
            return False

        if parameters is not None and not isinstance(parameters, dict):
            _log("warning", f"Los parámetros de {action_name} deben ser un diccionario")
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
            _log(
                "warning",
                f"[ACTION-REGISTRY] Parámetros requeridos faltantes para {action_name}: {missing_required}",
                "action_registry.py",
                "validate_action",
                671,
            )
            return False

        # Validar parámetros desconocidos
        unknown_params = []
        if not action_info.accepts_extra_parameters:
            for param_name in safe_parameters:
                if param_name not in definitions:
                    unknown_params.append(param_name)

        if unknown_params:
            _log(
                "warning",
                f"[ACTION-REGISTRY] Parámetros desconocidos para {action_name}: {unknown_params}",
                "action_registry.py",
                "validate_action",
                680,
            )
            return False

        # Validar tipos de parámetros
        type_errors = []
        for param_name, value in safe_parameters.items():
            info = definitions.get(param_name, {})
            expected_type = info.get("type", "any") if isinstance(info, dict) else "any"
            if not self._validate_value_type(value, expected_type):
                type_errors.append(
                    f"{param_name}: {type(value)} (esperado: {expected_type})"
                )

        if type_errors:
            _log(
                "warning",
                f"[ACTION-REGISTRY] Errores de tipo en {action_name}: {type_errors}",
                "action_registry.py",
                "validate_action",
                692,
            )
            return False

        _log(
            "debug",
            f"[ACTION-REGISTRY] Validación exitosa para {action_name}",
            "action_registry.py",
            "validate_action",
            695,
        )
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
            _log(
                "debug",
                f"[ACTION-REGISTRY] Acción no disponible: {action_name} (no encontrada)",
                "action_registry.py",
                "can_execute",
                691,
            )
            return False

        if parameters is not None and not isinstance(parameters, dict):
            _log("debug", f"Acción {action_name} no disponible: parámetros no válidos")
            return False
        safe_parameters = dict(parameters or {})
        if not self.validate_action(action_name, safe_parameters):
            _log(
                "debug",
                f"[ACTION-REGISTRY] Acción {action_name} no disponible: validación fallida",
                "action_registry.py",
                "can_execute",
                696,
            )
            return False

        if check_preconditions and state is not None:
            preconditions_met = action_info.matches_preconditions(state)
            if not preconditions_met:
                _log(
                    "debug",
                    f"[ACTION-REGISTRY] Acción {action_name} no disponible: precondiciones no cumplidas",
                    "action_registry.py",
                    "can_execute",
                    702,
                )
            else:
                _log(
                    "debug",
                    f"[ACTION-REGISTRY] Acción {action_name} disponible: precondiciones cumplidas",
                    "action_registry.py",
                    "can_execute",
                    704,
                )
            return preconditions_met
        else:
            _log(
                "debug",
                f"[ACTION-REGISTRY] Acción {action_name} disponible (sin verificación de precondiciones)",
                "action_registry.py",
                "can_execute",
                707,
            )
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
        """Ejecuta la función registrada y registra éxito/fallo sin ocultar errores.

        Los efectos declarados sobre el World State se aplican explícitamente a
        través de ``ActionInfo.apply_effects``; esta función solo ejecuta la
        capacidad real y registra la telemetría de la llamada.
        """
        with self._lock:
            self._execution_count += 1
            execution_number = self._execution_count
        prediction_memory = None
        success = False
        try:
            _log(
                "info",
                f"[ACTION-REGISTRY] Ejecutando acción {action_name} (#{execution_number})",
            )
            action_info = self.get_action(action_name)
            if action_info is None:
                raise ValueError(f"Acción no encontrada: {action_name}")
            if not callable(action_info.function):
                raise ValueError(
                    f"La acción no tiene función ejecutable: {action_name}"
                )
            if parameters is not None and not isinstance(parameters, dict):
                raise TypeError("parameters debe ser un diccionario")

            safe_parameters = dict(parameters or {})
            if not self.validate_action(action_name, safe_parameters):
                raise ValueError(f"Parámetros inválidos para la acción: {action_name}")

            try:
                prediction_memory = get_prediction_memory()
            except Exception as exc:
                _log("debug", f"Memoria predictiva no disponible: {exc}")

            result = action_info.function(**safe_parameters)
            success = True
            _log(
                "info",
                f"[ACTION-REGISTRY] Acción {action_name} ejecutada correctamente",
            )
            return result
        except Exception as exc:
            with self._lock:
                self._error_count += 1
                error_number = self._error_count
            _log(
                "error",
                f"[ACTION-REGISTRY] Falló {action_name} (error #{error_number}): {exc}",
            )
            raise
        finally:
            # La persistencia de aprendizaje nunca debe alterar el resultado real.
            if prediction_memory is None:
                try:
                    prediction_memory = get_prediction_memory()
                except Exception:
                    prediction_memory = None
            try:
                recorder = getattr(prediction_memory, "record_command", None)
                if callable(recorder):
                    recorder(
                        command=action_name, success=success, source="action_registry"
                    )
            except Exception as memory_error:
                _log(
                    "warning",
                    f"No se pudo registrar {action_name} en memoria predictiva: {memory_error}",
                )

    def list_actions(self, category: Optional[str] = None) -> List[str]:
        with self._lock:
            if category:
                return [
                    name
                    for name in self.categories.get(category, [])
                    if name in self.actions
                ]
            return list(self.actions.keys())

    def get_action_categories(self) -> List[str]:
        with self._lock:
            return list(self.categories.keys())

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Devuelve una instantánea consistente de las métricas del registro."""
        with self._lock:
            actions = list(self.actions.values())
            categories = {
                category: list(names) for category, names in self.categories.items()
            }
            registrations = self._action_count
            executions = self._execution_count
            errors = self._error_count

        stats = {
            "total_actions": len(actions),
            "total_categories": len(categories),
            "total_registrations": registrations,
            "total_executions": executions,
            "total_errors": errors,
            "categories": list(categories.keys()),
            "actions_by_category": {
                category: len(names) for category, names in categories.items()
            },
            "plannable_actions": sum(1 for action in actions if action.planner_enabled),
            "average_cost": sum(action.cost for action in actions) / len(actions)
            if actions
            else 0.0,
            "success_rate": (executions - errors) / max(executions, 1) * 100.0,
            "last_registered": max(
                actions, key=lambda item: item._registered_at, default=None
            ),
        }
        if executions and executions % 50 == 0:
            _log(
                "info",
                f"[ACTION-REGISTRY] Estadísticas: {stats['total_actions']} acciones, "
                f"{stats['success_rate']:.1f}% de éxito",
            )
        return stats

    def optimize_logging(self) -> None:
        """Optimiza el sistema de logging eliminando mensajes redundantes y mejorando la información."""
        # Aquí se podrían implementar estrategias de logging más avanzadas
        # como batching, niveles dinámicos, etc.
        _log(
            "info",
            "[ACTION-REGISTRY] Sistema de logging optimizado",
            "action_registry.py",
            "optimize_logging",
            794,
        )


_action_registry: Optional[ActionRegistry] = None
_action_registry_lock = threading.RLock()


def get_action_registry() -> ActionRegistry:
    """Devuelve el registro compartido, creado de forma segura entre hilos."""
    global _action_registry
    with _action_registry_lock:
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
