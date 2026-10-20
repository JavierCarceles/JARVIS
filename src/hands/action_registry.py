"""Registro centralizado de acciones para JARVIS.

Este módulo define el contrato entre las capacidades ejecutables y el sistema
que las planifica. Mantiene separadas la definición de acciones, la validación
de parámetros, las precondiciones/efectos y la ejecución de la capacidad real.

Las funciones y callbacks no se serializan; las reglas declarativas sí.
La actualización del World State después de ejecutar una acción pertenece a la
capa que verifica su resultado, no al registro.
"""

from __future__ import annotations

import importlib
import inspect
import math
import threading
import time
import types
from collections.abc import Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

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


# ---------------------------------------------------------------------------
# Logging and callback helpers
# ---------------------------------------------------------------------------
def _log(level: str, message: str, *, function: str = "action_registry") -> None:
    """Usa el logger del proyecto sin hacer que un fallo de logging rompa JARVIS."""
    normalized = str(level).lower()
    try:
        printer = getattr(logger, "_print_log", None)
        if callable(printer):
            printer(normalized, message, "action_registry.py", function, 0)
            return
        writer = getattr(logger, normalized, None)
        if not callable(writer) and normalized == "warning":
            writer = getattr(logger, "warn", None)
        if callable(writer):
            writer(message)
    except Exception:
        # La observabilidad no debe sustituir el resultado de la operación.
        pass


def _call_compatible(
    callback: Callable[..., Any], candidates: Sequence[Tuple[Tuple[Any, ...], Dict[str, Any]]]
) -> Any:
    """Elige una firma compatible antes de invocar, sin repetir callbacks.

    No se usa un ``except TypeError: volver a llamar``: el TypeError podría
    haberse producido dentro del callback después de efectos secundarios.
    """
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        if not candidates:
            return callback()
        args, kwargs = candidates[0]
        return callback(*args, **kwargs)

    for args, kwargs in candidates:
        try:
            signature.bind(*args, **kwargs)
        except TypeError:
            continue
        return callback(*args, **kwargs)

    # Produce el error normal de Python con la primera firma candidata para
    # conservar un diagnóstico reconocible para el consumidor.
    args, kwargs = candidates[0] if candidates else ((), {})
    signature.bind(*args, **kwargs)
    return callback(*args, **kwargs)  # pragma: no cover - bind siempre falla aquí


def _state_to_mapping(state: Any) -> Dict[str, Any]:
    """Obtiene una vista de estado compatible con los evaluadores declarativos."""
    if state is None:
        return {}
    if isinstance(state, dict):
        return dict(state)
    if isinstance(state, Mapping):
        return dict(state.items())

    for method_name in ("to_dict", "model_dump", "as_dict"):
        method = getattr(state, method_name, None)
        if callable(method):
            try:
                result = method()
                if isinstance(result, Mapping):
                    return dict(result.items())
            except Exception:
                pass

    if is_dataclass(state) and not isinstance(state, type):
        try:
            return {item.name: getattr(state, item.name) for item in fields(state)}
        except Exception:
            return {}

    try:
        return dict(vars(state))
    except (TypeError, ValueError):
        return {}


def _format_type_name(value: Any) -> str:
    """Devuelve un nombre legible de tipo y apto para serialización JSON."""
    if value is Any:
        return "Any"
    if value is None:
        return "None"
    if value is type(None):
        return "NoneType"
    if isinstance(value, type):
        return value.__name__
    origin = get_origin(value)
    args = get_args(value)
    if origin is not None:
        origin_name = getattr(origin, "__name__", str(origin).replace("typing.", ""))
        if origin in (Union, types.UnionType):
            return "Union[" + ", ".join(_format_type_name(arg) for arg in args) + "]"
        if origin is Literal:
            return "Literal[" + ", ".join(repr(arg) for arg in args) + "]"
        return f"{origin_name}[{', '.join(_format_type_name(arg) for arg in args)}]"
    return str(value).replace("typing.", "")


def _serialize_rule(value: Any, _seen: Optional[set[int]] = None) -> Any:
    """Serializa reglas sin intentar serializar callbacks ni ciclos de objetos."""
    if _seen is None:
        _seen = set()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _serialize_rule(value.value, _seen)
    if isinstance(value, type) or get_origin(value) is not None:
        return _format_type_name(value)
    if callable(value):
        return "FUNCION_NO_SERIALIZABLE"
    if isinstance(value, Path):
        return str(value)

    object_id = id(value)
    if object_id in _seen:
        return "REFERENCIA_CIRCULAR_NO_SERIALIZABLE"

    if isinstance(value, Condition):
        _seen.add(object_id)
        try:
            condition_type = getattr(value, "type", None)
            return {
                "type": _serialize_rule(getattr(condition_type, "value", condition_type), _seen),
                "key": _serialize_rule(getattr(value, "key", None), _seen),
                "expected_value": _serialize_rule(getattr(value, "expected_value", None), _seen),
                "description": getattr(value, "description", ""),
                "parameters": _serialize_rule(getattr(value, "parameters", {}), _seen),
                "function": (
                    "FUNCION_NO_SERIALIZABLE"
                    if getattr(value, "function", None) is not None
                    else None
                ),
            }
        finally:
            _seen.discard(object_id)

    if isinstance(value, Effect):
        _seen.add(object_id)
        try:
            effect_type = getattr(value, "type", None)
            return {
                "type": _serialize_rule(getattr(effect_type, "value", effect_type), _seen),
                "key": _serialize_rule(getattr(value, "key", None), _seen),
                "value": _serialize_rule(getattr(value, "value", None), _seen),
                "description": getattr(value, "description", ""),
                "parameters": _serialize_rule(getattr(value, "parameters", {}), _seen),
                "cumulative": bool(getattr(value, "cumulative", False)),
                "function": (
                    "FUNCION_NO_SERIALIZABLE"
                    if getattr(value, "function", None) is not None
                    else None
                ),
            }
        finally:
            _seen.discard(object_id)

    if isinstance(value, Mapping):
        _seen.add(object_id)
        try:
            return {str(key): _serialize_rule(item, _seen) for key, item in value.items()}
        finally:
            _seen.discard(object_id)

    if isinstance(value, (list, tuple, set, frozenset)):
        _seen.add(object_id)
        try:
            items = list(value)
            if isinstance(value, (set, frozenset)):
                items.sort(key=repr)
            return [_serialize_rule(item, _seen) for item in items]
        finally:
            _seen.discard(object_id)

    if is_dataclass(value) and not isinstance(value, type):
        _seen.add(object_id)
        try:
            return {
                item.name: _serialize_rule(getattr(value, item.name), _seen)
                for item in fields(value)
            }
        finally:
            _seen.discard(object_id)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
            if converted is not value:
                return _serialize_rule(converted, _seen)
        except Exception:
            pass

    # Se evita devolver objetos arbitrarios que json.dumps no pueda serializar.
    return str(value)


def _get_state_value(state: Any, key: Any, default: Any = None) -> Any:
    """Obtiene un valor de un mapping, un objeto con ``get`` o un atributo."""
    if state is None or key is None or key == "":
        return default
    if isinstance(state, Mapping):
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
        except Exception:
            pass
    return getattr(state, str(key), default)


# ---------------------------------------------------------------------------
# Preconditions and effects
# ---------------------------------------------------------------------------
def _condition_from_dict(condition: Dict[str, Any]) -> Optional[Condition]:
    """Convierte un diccionario tipado al modelo canónico ``Condition``."""
    if "type" not in condition:
        return None

    raw_type = condition.get("type")
    try:
        from src.hands.planner.preconditions_effects_types import ConditionType

        if isinstance(raw_type, ConditionType):
            condition_type = raw_type
        else:
            raw = str(getattr(raw_type, "value", raw_type)).strip()
            try:
                condition_type = ConditionType(raw.lower())
            except ValueError:
                condition_type = ConditionType[raw.upper()]
    except (ImportError, AttributeError, KeyError, TypeError, ValueError):
        return None

    key = condition.get("key", condition.get("state"))
    expected = condition.get(
        "expected_value",
        condition.get("equals", condition.get("expected", condition.get("value"))),
    )
    function = condition.get("function")
    parameters = condition.get("parameters") or {}
    if not isinstance(parameters, Mapping):
        return None

    try:
        return Condition(
            type=condition_type,
            key=key,
            expected_value=expected,
            function=function if callable(function) else None,
            description=str(condition.get("description", "")),
            parameters=dict(parameters),
        )
    except (TypeError, ValueError):
        return None


def _evaluate_condition_object(state: Any, condition: Condition) -> bool:
    try:
        return bool(condition.evaluate(_state_to_mapping(state)))
    except Exception as exc:
        _log("warning", f"No se pudo evaluar una precondición: {exc}", function="_match_condition")
        return False


def _match_condition(state: Any, condition: Any) -> bool:
    """Evalúa una condición simple, compuesta, funcional o canónica."""
    if isinstance(condition, Condition):
        return _evaluate_condition_object(state, condition)

    if callable(condition):
        try:
            return bool(condition(state))
        except Exception as exc:
            _log("warning", f"Falló una precondición funcional: {exc}", function="_match_condition")
            return False

    if isinstance(condition, str):
        return bool(_get_state_value(state, condition, False))

    if isinstance(condition, Mapping):
        # Si declara un tipo, no convertir una condición desconocida a legacy:
        # un tipo inválido debe bloquear la acción de forma conservadora.
        if "type" in condition:
            condition_obj = _condition_from_dict(dict(condition))
            return False if condition_obj is None else _evaluate_condition_object(state, condition_obj)

        # Forma compuesta declarativa: {conditions: [...], operator/op: and|or}.
        if "conditions" in condition:
            operator = str(condition.get("operator", condition.get("op", "and"))).strip().lower()
            children = condition.get("conditions")
            if not isinstance(children, (list, tuple, set)):
                return False
            results = [_match_condition(state, child) for child in children]
            if operator == "or":
                return any(results)
            if operator == "and":
                return all(results)
            return False

        # Forma legacy explícita: {key/state: ..., value/equals: ...}.
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

        # Forma legacy tipo mapa: cada propiedad debe coincidir.
        return all(_get_state_value(state, key, None) == expected for key, expected in condition.items())

    if isinstance(condition, (list, tuple, set)):
        return all(_match_condition(state, child) for child in condition)

    return bool(condition)


def _matches_conditions(state: Any, conditions: Any) -> bool:
    """Evalúa una colección de precondiciones con semántica AND por defecto."""
    if conditions is None:
        return True
    if isinstance(conditions, (list, tuple, set, frozenset)):
        return all(_match_condition(state, condition) for condition in conditions)
    if isinstance(conditions, Mapping) and not conditions:
        return True
    return _match_condition(state, conditions)


def _apply_effect_value(
    effect: Any,
    current_state: Dict[str, Any],
    execution_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Aplica un efecto canónico, funcional o legacy sobre una copia del estado."""
    state = dict(current_state)

    if isinstance(effect, Effect):
        updated = _call_compatible(
            effect.apply,
            [((state, execution_result), {}), ((state,), {})],
        )
        if not isinstance(updated, dict):
            raise TypeError("Effect.apply debe devolver un dict de estado")
        return updated

    if callable(effect):
        updated = _call_compatible(
            effect,
            [((state, execution_result), {}), ((state,), {})],
        )
        if not isinstance(updated, dict):
            raise TypeError("Un efecto funcional debe devolver un dict de estado")
        return updated

    if isinstance(effect, str):
        effect_obj = Effect(type="state_set", key=effect, value=True)
        updated = _call_compatible(
            effect_obj.apply,
            [((state, execution_result), {}), ((state,), {})],
        )
        if not isinstance(updated, dict):
            raise TypeError("Effect.apply debe devolver un dict de estado")
        return updated

    if isinstance(effect, Mapping):
        function = effect.get("function")
        if callable(function):
            return _apply_effect_value(function, state, execution_result)

        effect_type = effect.get("type", "state_set")
        key = effect.get("key", effect.get("state"))
        if key is None and str(getattr(effect_type, "value", effect_type)).lower() != "composite":
            return state
        parameters = effect.get("parameters") or {}
        if not isinstance(parameters, Mapping):
            raise TypeError("Los parámetros de un efecto deben ser un mapping")
        effect_obj = Effect(
            type=effect_type,
            key=key,
            value=effect.get("value"),
            description=str(effect.get("description", "")),
            parameters=dict(parameters),
            cumulative=bool(effect.get("cumulative", False)),
        )
        updated = _call_compatible(
            effect_obj.apply,
            [((state, execution_result), {}), ((state,), {})],
        )
        if not isinstance(updated, dict):
            raise TypeError("Effect.apply debe devolver un dict de estado")
        return updated

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
    allow_extra_parameters: bool = False

    def __post_init__(self) -> None:
        self.action_type = _resolve_action_type(self.action_type)
        self.parameters = dict(self.parameters or {})
        self.tags = list(self.tags or [])
        self.dependencies = list(self.dependencies or [])
        self.required_resources = list(self.required_resources or [])
        self.preconditions_functions = list(self.preconditions_functions or [])
        self.effects_functions = list(self.effects_functions or [])
        self.confidence_threshold = _normalize_confidence(self.confidence_threshold)
        self.cost = _normalize_cost(self.cost)
        self.planner_enabled = bool(self.planner_enabled)
        self.allow_extra_parameters = bool(self.allow_extra_parameters)

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve metadatos serializables; nunca expone callbacks ejecutables."""
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
            "allow_extra_parameters": self.allow_extra_parameters,
            "preconditions_functions": "FUNCIONES_NO_SERIALIZABLES",
            "effects_functions": "FUNCIONES_NO_SERIALIZABLES",
        }

    def matches_preconditions(self, state: Any) -> bool:
        """Comprueba todas las precondiciones declarativas y funcionales."""
        if not _matches_conditions(state, self.preconditions):
            return False

        for precondition in self.preconditions_functions:
            if not callable(precondition):
                _log("warning", f"Precondición funcional inválida en {self.name}", function="matches_preconditions")
                return False
            try:
                if not bool(precondition(state)):
                    return False
            except Exception as exc:
                _log("warning", f"Falló una precondición de {self.name}: {exc}", function="matches_preconditions")
                return False
        return True

    def verify_success(self, result: Any = None, *args: Any, **kwargs: Any) -> bool:
        """Ejecuta el verificador configurado sin invocarlo más de una vez."""
        if self.success_checker is None:
            return True
        if not callable(self.success_checker):
            _log("warning", f"Verificador de éxito inválido para {self.name}", function="verify_success")
            return False
        try:
            candidates = [((result, *args), kwargs), ((result,), {}), ((), {})]
            return bool(_call_compatible(self.success_checker, candidates))
        except Exception as exc:
            _log("warning", f"Falló la verificación de {self.name}: {exc}", function="verify_success")
            return False

    def apply_effects(
        self,
        current_state: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aplica efectos de forma acumulativa o devuelve el estado original."""
        original_state = dict(current_state or {})
        state = dict(original_state)
        result = dict(execution_result or {})

        try:
            effects = [] if self.effects is None else self.effects
            if not isinstance(effects, (list, tuple, set, frozenset)):
                effects = [effects]
            for effect in effects:
                state = _apply_effect_value(effect, state, result)

            for effect_function in self.effects_functions:
                if not callable(effect_function):
                    raise TypeError(f"Efecto funcional inválido en {self.name}")
                updated_state = _call_compatible(
                    effect_function,
                    [((state, result), {}), ((state,), {})],
                )
                if not isinstance(updated_state, dict):
                    raise TypeError("El efecto funcional debe devolver un dict")
                state = updated_state
            return state
        except Exception as exc:
            _log("error", f"No se pudieron aplicar todos los efectos de {self.name}: {exc}", function="apply_effects")
            return original_state


def _normalize_cost(cost: Any) -> float:
    try:
        normalized = float(cost)
    except (TypeError, ValueError, OverflowError):
        normalized = 1.0
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError("El coste de una acción debe ser finito y no negativo")
    return normalized


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.8
    if not math.isfinite(confidence):
        confidence = 0.8
    return max(0.0, min(1.0, confidence))


def _resolve_action_type(raw_type: Union[str, ActionType]) -> ActionType:
    if isinstance(raw_type, ActionType):
        return raw_type
    normalized = str(getattr(raw_type, "value", raw_type)).strip().lower()
    for action_type in ActionType:
        if action_type.value == normalized or action_type.name.lower() == normalized:
            return action_type
    raise ValueError(f"ActionType desconocido: {raw_type}")


def _parse_type_string(type_name: str) -> Any:
    """Resuelve formas habituales de anotaciones expresadas como texto."""
    name = type_name.strip().replace("typing.", "")
    aliases: Dict[str, Any] = {
        "any": Any,
        "object": object,
        "none": type(None),
        "nonetype": type(None),
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
    }
    if name.lower() in aliases:
        return aliases[name.lower()]

    # Admitir Optional[T], Union[T, U] y los contenedores más frecuentes sin eval.
    lowered = name.lower()
    for prefix, constructor in (("optional[", Optional), ("list[", List), ("dict[", Dict), ("tuple[", Tuple)):
        if lowered.startswith(prefix) and name.endswith("]"):
            inner = name[name.find("[") + 1 : -1]
            parts = _split_type_arguments(inner)
            parsed = tuple(_parse_type_string(part) for part in parts)
            if any(item is None for item in parsed):
                return None
            try:
                if constructor is Optional and len(parsed) == 1:
                    return Optional[parsed[0]]
                if constructor is List and len(parsed) == 1:
                    return List[parsed[0]]
                if constructor is Dict and len(parsed) == 2:
                    return Dict[parsed[0], parsed[1]]
                if constructor is Tuple and parsed:
                    if len(parsed) == 2 and parsed[1] is Ellipsis:
                        return Tuple[parsed[0], ...]
                    return Tuple[parsed]
            except (TypeError, AttributeError):
                return None

    if lowered.startswith("union[") and name.endswith("]"):
        parts = _split_type_arguments(name[name.find("[") + 1 : -1])
        parsed = tuple(_parse_type_string(part) for part in parts)
        if parsed and all(item is not None for item in parsed):
            try:
                return Union[parsed]
            except TypeError:
                return None
    if " | " in name:
        parts = [part.strip() for part in name.split("|")]
        parsed = [_parse_type_string(part) for part in parts]
        if parsed and all(item is not None for item in parsed):
            try:
                return Union[tuple(parsed)]
            except TypeError:
                return None
    return None


def _split_type_arguments(value: str) -> List[str]:
    """Divide argumentos de tipo respetando corchetes anidados."""
    parts: List[str] = []
    depth = 0
    quote: Optional[str] = None
    start = 0
    for index, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


class ActionRegistry:
    """Registro central, thread-safe, de acciones/capacidades disponibles."""

    def __init__(self) -> None:
        self.actions: Dict[str, ActionInfo] = {}
        self.categories: Dict[str, List[str]] = {}
        self._registered_modules: set[str] = set()
        self._action_count = 0
        self._execution_count = 0
        self._success_count = 0
        self._error_count = 0
        self._lock = threading.RLock()
        _log("info", "[ACTION-REGISTRY] Registro de acciones inicializado", function="__init__")

    @staticmethod
    def _extract_parameters(func: Callable) -> Dict[str, Any]:
        """Extrae tipo, valor por defecto y obligatoriedad de la firma real."""
        signature = inspect.signature(func)
        try:
            type_hints = get_type_hints(func)
        except Exception:
            type_hints = {}

        extracted: Dict[str, Any] = {}
        for param_name, param in signature.parameters.items():
            if param_name in {"self", "cls"} or param.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue
            annotation = type_hints.get(param_name, param.annotation)
            parameter_type: Any = "any" if annotation is inspect.Parameter.empty else annotation
            default = None if param.default is inspect.Parameter.empty else param.default
            extracted[param_name] = {
                "type": parameter_type,
                "default": default,
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
        if not isinstance(name, str) or not name.strip():
            raise ValueError("El nombre de una acción debe ser una cadena no vacía")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("La categoría de una acción debe ser una cadena no vacía")

        normalized_action_type = _resolve_action_type(action_type)
        normalized_cost = _normalize_cost(cost)
        normalized_confidence = _normalize_confidence(confidence_threshold)
        explicit_parameters = None if parameters is None else dict(parameters)

        def decorator(func: Callable) -> Callable:
            if not callable(func):
                raise TypeError(f"La acción {name} debe asociarse a una función invocable")

            action_parameters = (
                self._extract_parameters(func)
                if explicit_parameters is None
                else dict(explicit_parameters)
            )
            try:
                signature = inspect.signature(func)
                allow_extra_parameters = any(
                    param.kind == inspect.Parameter.VAR_KEYWORD
                    for param in signature.parameters.values()
                )
            except (TypeError, ValueError):
                allow_extra_parameters = False

            action_info = ActionInfo(
                name=name.strip(),
                description=str(description),
                action_type=normalized_action_type,
                function=func,
                parameters=action_parameters,
                module=getattr(func, "__module__", ""),
                category=category.strip(),
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
                allow_extra_parameters=allow_extra_parameters,
            )
            setattr(func, "_jarvis_action_info", action_info)
            self._store_action_info(action_info)
            return func

        return decorator

    def register_module(self, module_path: str) -> None:
        """Importa un módulo y registra sus funciones decoradas una sola vez."""
        if not isinstance(module_path, str) or not module_path.strip():
            _log("warning", "No se puede registrar un módulo con nombre vacío", function="register_module")
            return
        module_path = module_path.strip()
        with self._lock:
            if module_path in self._registered_modules:
                _log("debug", f"[ACTION-REGISTRY] Módulo ya registrado: {module_path}", function="register_module")
                return

        try:
            module = importlib.import_module(module_path)
            discovered: Dict[str, ActionInfo] = {}
            for _, obj in inspect.getmembers(module):
                action_info = getattr(obj, "_jarvis_action_info", None)
                if isinstance(action_info, ActionInfo):
                    discovered[action_info.name] = action_info

            for action_info in discovered.values():
                self._store_action_info(action_info)
            with self._lock:
                self._registered_modules.add(module_path)
            _log(
                "info" if discovered else "debug",
                f"[ACTION-REGISTRY] Módulo {module_path}: {len(discovered)} acciones registradas",
                function="register_module",
            )
        except ImportError as exc:
            _log("warning", f"[ACTION-REGISTRY] Error al importar módulo {module_path}: {exc}", function="register_module")
        except Exception as exc:
            _log("error", f"[ACTION-REGISTRY] Error al registrar módulo {module_path}: {exc}", function="register_module")

    def _store_action_info(self, action_info: ActionInfo) -> None:
        """Guarda la acción y conserva la coherencia entre acciones y categorías."""
        with self._lock:
            previous = self.actions.get(action_info.name)
            if previous is not None and previous.category != action_info.category:
                old_names = self.categories.get(previous.category, [])
                if action_info.name in old_names:
                    old_names.remove(action_info.name)
                if not old_names:
                    self.categories.pop(previous.category, None)

            self.actions[action_info.name] = action_info
            action_names = self.categories.setdefault(action_info.category, [])
            if action_info.name not in action_names:
                action_names.append(action_info.name)
            self._action_count += 1
            setattr(action_info, "_registered_at", time.time())
            current_count = self._action_count

        if current_count % 10 == 0:
            _log("info", f"[ACTION-REGISTRY] Registradas {current_count} operaciones de registro", function="_store_action_info")

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
                name: info for name, info in self.actions.items() if info.planner_enabled
            }

    def get_actions_for_planner(self) -> List[Dict[str, Any]]:
        with self._lock:
            actions = list(self.actions.values())
        return [info.to_dict() for info in actions if info.planner_enabled]

    def get_actions_for_llama(self) -> List[Dict[str, Any]]:
        with self._lock:
            actions = [info.to_dict() for info in self.actions.values()]
        _log(
            "info" if actions else "warning",
            f"[ACTION-REGISTRY] Enviando {len(actions)} acciones al LLM",
            function="get_actions_for_llama",
        )
        return actions

    @staticmethod
    def _validate_value_type(value: Any, expected_type: Any) -> bool:
        """Valida tipos Python y anotaciones parametrizadas habituales."""
        if expected_type in (None, "any", "Any") or expected_type is Any:
            return True

        if isinstance(expected_type, str):
            parsed_type = _parse_type_string(expected_type)
            if parsed_type is not None:
                expected_type = parsed_type
            else:
                # Un forward reference que no se pudo resolver no debe romper
                # acciones ya registradas; sus parámetros siguen siendo validados
                # en presencia/nombre. El contrato se puede hacer explícito en
                # metadata con un tipo reconocido.
                return True

        origin = get_origin(expected_type)
        args = get_args(expected_type)

        if origin is Annotated:
            return ActionRegistry._validate_value_type(value, args[0]) if args else True
        if origin in (Union, types.UnionType):
            return any(ActionRegistry._validate_value_type(value, arg) for arg in args)
        if origin is Literal:
            return any(type(value) is type(choice) and value == choice for choice in args)

        if expected_type is type(None):
            return value is None
        if expected_type is int:
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type is float:
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
        if expected_type is bool:
            return isinstance(value, bool)
        if expected_type is str:
            return isinstance(value, str)

        if origin in (list, List):
            return isinstance(value, list) and (
                not args or all(ActionRegistry._validate_value_type(item, args[0]) for item in value)
            )
        if origin in (dict, Dict, Mapping):
            if not isinstance(value, Mapping):
                return False
            if len(args) == 2:
                return all(
                    ActionRegistry._validate_value_type(key, args[0])
                    and ActionRegistry._validate_value_type(item, args[1])
                    for key, item in value.items()
                )
            return True
        if origin in (tuple, Tuple):
            if not isinstance(value, tuple):
                return False
            if not args:
                return True
            if len(args) == 2 and args[1] is Ellipsis:
                return all(ActionRegistry._validate_value_type(item, args[0]) for item in value)
            return len(value) == len(args) and all(
                ActionRegistry._validate_value_type(item, item_type)
                for item, item_type in zip(value, args)
            )
        if origin in (set, AbstractSet):
            return isinstance(value, (set, frozenset)) and (
                not args or all(ActionRegistry._validate_value_type(item, args[0]) for item in value)
            )
        if origin in (Sequence,):
            return isinstance(value, Sequence) and not isinstance(value, (str, bytes))

        if isinstance(expected_type, type):
            return isinstance(value, expected_type)

        # Typing aliases y forward references no resueltas: compatibilidad
        # conservadora hasta que el módulo proporcione una anotación resoluble.
        return True

    def validate_action(self, action_name: str, parameters: Optional[Dict[str, Any]]) -> bool:
        """Comprueba presencia, nombres y tipos de parámetros sin ejecutar la acción."""
        action_info = self.get_action(action_name)
        if action_info is None:
            _log("error", f"[ACTION-REGISTRY] Acción no encontrada: {action_name}", function="validate_action")
            return False
        if parameters is not None and not isinstance(parameters, Mapping):
            _log("warning", f"Los parámetros de {action_name} deben ser un mapping", function="validate_action")
            return False

        safe_parameters = dict(parameters or {})
        if any(not isinstance(name, str) for name in safe_parameters):
            _log("warning", f"Hay nombres de parámetros no textuales para {action_name}", function="validate_action")
            return False

        definitions = action_info.parameters or {}
        missing_required = [
            param_name
            for param_name, param_info in definitions.items()
            if isinstance(param_info, Mapping)
            and bool(param_info.get("required", False))
            and param_name not in safe_parameters
        ]
        if missing_required:
            _log("warning", f"Parámetros requeridos faltantes para {action_name}: {missing_required}", function="validate_action")
            return False

        unknown_params = [name for name in safe_parameters if name not in definitions]
        if unknown_params and not action_info.allow_extra_parameters:
            _log("warning", f"Parámetros desconocidos para {action_name}: {unknown_params}", function="validate_action")
            return False

        type_errors: List[str] = []
        for param_name, value in safe_parameters.items():
            info = definitions.get(param_name)
            if info is None and action_info.allow_extra_parameters:
                continue
            if not isinstance(info, Mapping):
                info = {}
            expected_type = info.get("type", "any")
            if not self._validate_value_type(value, expected_type):
                type_errors.append(
                    f"{param_name}: recibido {type(value).__name__}, esperado {_format_type_name(expected_type)}"
                )

        if type_errors:
            _log("warning", f"Errores de tipo en {action_name}: {type_errors}", function="validate_action")
            return False
        return True

    def can_execute(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        state: Any = None,
        check_preconditions: bool = True,
    ) -> bool:
        """Determina si una acción registrada se puede ejecutar en el estado dado."""
        action_info = self.get_action(action_name)
        if action_info is None or action_info.function is None:
            return False
        if not self.validate_action(action_name, parameters):
            return False
        if check_preconditions and state is not None:
            return action_info.matches_preconditions(state)
        return True

    def get_action_cost(self, action_name: str) -> float:
        action_info = self.get_action(action_name)
        if action_info is None:
            raise ValueError(f"Acción no encontrada: {action_name}")
        return action_info.cost

    def _record_execution(self, success: bool) -> None:
        with self._lock:
            self._execution_count += 1
            if success:
                self._success_count += 1
            else:
                self._error_count += 1
            execution_number = self._execution_count
            error_number = self._error_count
        _log(
            "info" if success else "error",
            f"[ACTION-REGISTRY] Ejecución #{execution_number}: {'correcta' if success else f'fallida (error #{error_number})'}",
            function="execute_action",
        )

    @staticmethod
    def _record_prediction(prediction_memory: Any, action_name: str, success: bool) -> None:
        if prediction_memory is None:
            return
        try:
            recorder = getattr(prediction_memory, "record_command", None)
            if callable(recorder):
                recorder(command=action_name, success=success, source="action_registry")
        except Exception as exc:
            _log("warning", f"No se pudo registrar el resultado en memoria predictiva: {exc}", function="execute_action")

    def execute_action(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Ejecuta la función registrada y propaga sus excepciones originales.

        No actualiza el World State: el Executor/Verification debe confirmar el
        resultado y aplicar después los efectos declarativos correspondientes.
        """
        try:
            prediction_memory = get_prediction_memory()
        except Exception:
            prediction_memory = None

        action_info = self.get_action(action_name)
        if action_info is None:
            self._record_execution(False)
            self._record_prediction(prediction_memory, action_name, False)
            raise ValueError(f"Acción no encontrada: {action_name}")
        if action_info.function is None:
            self._record_execution(False)
            self._record_prediction(prediction_memory, action_name, False)
            raise ValueError(f"La acción no tiene función ejecutable: {action_name}")

        if parameters is not None and not isinstance(parameters, Mapping):
            self._record_execution(False)
            self._record_prediction(prediction_memory, action_name, False)
            raise ValueError(f"Los parámetros de {action_name} deben ser un mapping")
        safe_parameters = dict(parameters or {})
        if not self.validate_action(action_name, safe_parameters):
            self._record_execution(False)
            self._record_prediction(prediction_memory, action_name, False)
            raise ValueError(f"Parámetros inválidos para la acción: {action_name}")

        try:
            result = action_info.function(**safe_parameters)
        except Exception:
            self._record_execution(False)
            self._record_prediction(prediction_memory, action_name, False)
            raise

        self._record_execution(True)
        self._record_prediction(prediction_memory, action_name, True)
        return result

    def list_actions(self, category: Optional[str] = None) -> List[str]:
        with self._lock:
            if category:
                return [name for name in self.categories.get(category, []) if name in self.actions]
            return list(self.actions.keys())

    def get_action_categories(self) -> List[str]:
        with self._lock:
            return list(self.categories.keys())

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Devuelve estadísticas del registro a partir de contadores reales."""
        with self._lock:
            actions = list(self.actions.values())
            categories = {category: len(names) for category, names in self.categories.items()}
            execution_count = self._execution_count
            error_count = self._error_count
            success_count = self._success_count
            registration_count = self._action_count
        latest = max(actions, key=lambda item: getattr(item, "_registered_at", 0), default=None)
        stats: Dict[str, Any] = {
            "total_actions": len(actions),
            "total_categories": len(categories),
            "total_registrations": registration_count,
            "total_executions": execution_count,
            "total_errors": error_count,
            "total_successes": success_count,
            "categories": list(categories.keys()),
            "actions_by_category": categories,
            "plannable_actions": sum(1 for action in actions if action.planner_enabled),
            "average_cost": sum(action.cost for action in actions) / len(actions) if actions else 0.0,
            "success_rate": (success_count / execution_count * 100.0) if execution_count else 0.0,
            # Conserva el contrato previo: el valor es ActionInfo, no solo su nombre.
            "last_registered": latest,
        }
        if execution_count and execution_count % 50 == 0:
            _log("info", f"[ACTION-REGISTRY] {stats['total_actions']} acciones; éxito {stats['success_rate']:.1f}%", function="get_optimization_stats")
        return stats

    def optimize_logging(self) -> None:
        """Punto de compatibilidad para configurar logging sin cambiar el contrato."""
        _log("info", "[ACTION-REGISTRY] Sistema de logging del registro operativo", function="optimize_logging")


_action_registry: Optional[ActionRegistry] = None
_action_registry_lock = threading.Lock()


def get_action_registry() -> ActionRegistry:
    """Obtiene el singleton de ActionRegistry con inicialización segura."""
    global _action_registry
    if _action_registry is None:
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
    """Decorador de conveniencia para registrar acciones en el singleton."""
    return get_action_registry().register_action(
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
    """Registra acciones decoradas que se encuentren en el módulo indicado."""
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
