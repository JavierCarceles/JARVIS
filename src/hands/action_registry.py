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
<<<<<<< HEAD
import ast
import threading
import time
import types
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import (
=======
import threading
import time
import types
from collections.abc import Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Annotated,
>>>>>>> 8d6d091 (correccion pull)
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
<<<<<<< HEAD
=======
    Tuple,
>>>>>>> 8d6d091 (correccion pull)
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


<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)


def _get_state_value(state: Any, key: Any, default: Any = None) -> Any:
    """Obtiene un valor de un mapping, un objeto con ``get`` o un atributo."""
    if state is None or key is None or key == "":
        return default
<<<<<<< HEAD
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
=======
    if isinstance(state, Mapping):
        return state.get(key, default)
>>>>>>> 8d6d091 (correccion pull)

    getter = getattr(state, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            try:
                return getter(key)
            except Exception:
                pass
<<<<<<< HEAD

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
=======
        except Exception:
            pass
    return getattr(state, str(key), default)
>>>>>>> 8d6d091 (correccion pull)


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
<<<<<<< HEAD
        try:
            return bool(condition.evaluate(_state_to_dict(state)))
        except Exception:
            return False
=======
        return _evaluate_condition_object(state, condition)
>>>>>>> 8d6d091 (correccion pull)

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
<<<<<<< HEAD
            operator = (
                str(condition.get("operator", condition.get("op", "and")))
                .strip()
                .lower()
            )
            children = condition.get("conditions") or []
            if operator not in {"and", "or"} or not isinstance(
                children, (list, tuple, set)
            ):
=======
            operator = str(condition.get("operator", condition.get("op", "and"))).strip().lower()
            children = condition.get("conditions")
            if not isinstance(children, (list, tuple, set)):
>>>>>>> 8d6d091 (correccion pull)
                return False
            results = [_match_condition(state, child) for child in children]
            if operator == "or":
                return any(results)
            if operator == "and":
                return all(results)
            return False

<<<<<<< HEAD
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
=======
        # Forma legacy explícita: {key/state: ..., value/equals: ...}.
>>>>>>> 8d6d091 (correccion pull)
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
<<<<<<< HEAD
    """Aplica un efecto mediante el modelo canónico o compatibilidad legacy."""
    state = _safe_copy(dict(current_state))
=======
    """Aplica un efecto canónico, funcional o legacy sobre una copia del estado."""
    state = dict(current_state)
>>>>>>> 8d6d091 (correccion pull)

    if isinstance(effect, Effect):
        updated = _call_compatible(
            effect.apply,
            [((state, execution_result), {}), ((state,), {})],
        )
        if not isinstance(updated, dict):
            raise TypeError("Effect.apply debe devolver un dict de estado")
        return updated

    if callable(effect):
<<<<<<< HEAD
        updated = _invoke_compatible(
=======
        updated = _call_compatible(
>>>>>>> 8d6d091 (correccion pull)
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
        effect_type = getattr(effect_type, "value", effect_type)
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
<<<<<<< HEAD
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
=======
    allow_extra_parameters: bool = False

    def __post_init__(self) -> None:
        self.action_type = _resolve_action_type(self.action_type)
>>>>>>> 8d6d091 (correccion pull)
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
<<<<<<< HEAD
            "accepts_extra_parameters": self.accepts_extra_parameters,
=======
            "allow_extra_parameters": self.allow_extra_parameters,
>>>>>>> 8d6d091 (correccion pull)
            "preconditions_functions": "FUNCIONES_NO_SERIALIZABLES",
            "effects_functions": "FUNCIONES_NO_SERIALIZABLES",
        }

    def matches_preconditions(self, state: Any) -> bool:
        """Comprueba todas las precondiciones declarativas y funcionales."""
        if not _matches_conditions(state, self.preconditions):
            return False

<<<<<<< HEAD
        for precond_func in self.preconditions_functions:
            if not callable(precond_func):
                _log(
                    "warning", f"Precondición no invocable configurada para {self.name}"
                )
=======
        for precondition in self.preconditions_functions:
            if not callable(precondition):
                _log("warning", f"Precondición funcional inválida en {self.name}", function="matches_preconditions")
>>>>>>> 8d6d091 (correccion pull)
                return False
            try:
                if not bool(precondition(state)):
                    return False
            except Exception as exc:
<<<<<<< HEAD
                _log("warning", f"Falló una precondición de {self.name}: {exc}")
=======
                _log("warning", f"Falló una precondición de {self.name}: {exc}", function="matches_preconditions")
>>>>>>> 8d6d091 (correccion pull)
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
<<<<<<< HEAD
            candidate_args = (result, *args)
            return bool(
                _invoke_compatible(
                    self.success_checker,
                    [(candidate_args, kwargs), ((result,), {}), ((), {})],
                )
            )
        except Exception as exc:
            _log("warning", f"El verificador de éxito de {self.name} falló: {exc}")
=======
            candidates = [((result, *args), kwargs), ((result,), {}), ((), {})]
            return bool(_call_compatible(self.success_checker, candidates))
        except Exception as exc:
            _log("warning", f"Falló la verificación de {self.name}: {exc}", function="verify_success")
>>>>>>> 8d6d091 (correccion pull)
            return False

    def apply_effects(
        self,
        current_state: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
<<<<<<< HEAD
        """Aplica efectos declarativos y funcionales de manera transaccional."""
        if current_state is not None and not isinstance(current_state, dict):
            raise TypeError("current_state debe ser un diccionario")
        if execution_result is not None and not isinstance(execution_result, dict):
            raise TypeError("execution_result debe ser un diccionario")
        original_state = _safe_copy(dict(current_state or {}))
        state = _safe_copy(original_state)
        result = _safe_copy(dict(execution_result or {}))
=======
        """Aplica efectos de forma acumulativa o devuelve el estado original."""
        original_state = dict(current_state or {})
        state = dict(original_state)
        result = dict(execution_result or {})
>>>>>>> 8d6d091 (correccion pull)

        try:
            effects = [] if self.effects is None else self.effects
            if not isinstance(effects, (list, tuple, set, frozenset)):
                effects = [effects]
            for effect in effects:
                state = _apply_effect_value(effect, state, result)

<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)
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


<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)
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
<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)

        extracted: Dict[str, Any] = {}
        for param_name, param in signature.parameters.items():
            if param_name in {"self", "cls"} or param.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue
<<<<<<< HEAD

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

=======
            annotation = type_hints.get(param_name, param.annotation)
            parameter_type: Any = "any" if annotation is inspect.Parameter.empty else annotation
            default = None if param.default is inspect.Parameter.empty else param.default
>>>>>>> 8d6d091 (correccion pull)
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

        if not str(name or "").strip():
            raise ValueError("El nombre de la acción no puede estar vacío")
        if not str(category or "").strip():
            category = "general"
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
<<<<<<< HEAD
                module=func.__module__,
                category=category,
                tags=_as_list(tags),
=======
                module=getattr(func, "__module__", ""),
                category=category.strip(),
                tags=list(tags or []),
>>>>>>> 8d6d091 (correccion pull)
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
<<<<<<< HEAD
                preconditions_functions=_as_list(preconditions_functions),
                effects_functions=_as_list(effects_functions),
=======
                preconditions_functions=list(preconditions_functions or []),
                effects_functions=list(effects_functions or []),
                allow_extra_parameters=allow_extra_parameters,
>>>>>>> 8d6d091 (correccion pull)
            )
            setattr(func, "_jarvis_action_info", action_info)
            self._store_action_info(action_info)
            return func

        return decorator

    def register_module(self, module_path: str) -> None:
<<<<<<< HEAD
        """Importa un módulo y registra sus acciones decoradas con logging optimizado."""
        if not isinstance(module_path, str) or not module_path.strip():
            raise ValueError("module_path debe ser una ruta de módulo no vacía")
        module_path = module_path.strip()
        with self._lock:
            if module_path in self._registered_modules:
                _log("debug", f"[ACTION-REGISTRY] Módulo ya registrado: {module_path}")
=======
        """Importa un módulo y registra sus funciones decoradas una sola vez."""
        if not isinstance(module_path, str) or not module_path.strip():
            _log("warning", "No se puede registrar un módulo con nombre vacío", function="register_module")
            return
        module_path = module_path.strip()
        with self._lock:
            if module_path in self._registered_modules:
                _log("debug", f"[ACTION-REGISTRY] Módulo ya registrado: {module_path}", function="register_module")
>>>>>>> 8d6d091 (correccion pull)
                return

        try:
            module = importlib.import_module(module_path)
            discovered: Dict[str, ActionInfo] = {}
            for _, obj in inspect.getmembers(module):
                action_info = getattr(obj, "_jarvis_action_info", None)
                if isinstance(action_info, ActionInfo):
                    discovered[action_info.name] = action_info

<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)

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
<<<<<<< HEAD
                name: info
                for name, info in self.actions.items()
                if info.planner_enabled
=======
                name: info for name, info in self.actions.items() if info.planner_enabled
>>>>>>> 8d6d091 (correccion pull)
            }

    def get_actions_for_planner(self) -> List[Dict[str, Any]]:
        with self._lock:
<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)

    def validate_action(self, action_name: str, parameters: Optional[Dict[str, Any]]) -> bool:
        """Comprueba presencia, nombres y tipos de parámetros sin ejecutar la acción."""
        action_info = self.get_action(action_name)
        if action_info is None:
<<<<<<< HEAD
            _log(
                "error",
                f"[ACTION-REGISTRY] Acción no encontrada: {action_name}",
                "action_registry.py",
                "validate_action",
                659,
            )
=======
            _log("error", f"[ACTION-REGISTRY] Acción no encontrada: {action_name}", function="validate_action")
            return False
        if parameters is not None and not isinstance(parameters, Mapping):
            _log("warning", f"Los parámetros de {action_name} deben ser un mapping", function="validate_action")
>>>>>>> 8d6d091 (correccion pull)
            return False

        if parameters is not None and not isinstance(parameters, dict):
            _log("warning", f"Los parámetros de {action_name} deben ser un diccionario")
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
<<<<<<< HEAD
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
=======
            _log("warning", f"Parámetros requeridos faltantes para {action_name}: {missing_required}", function="validate_action")
            return False

        unknown_params = [name for name in safe_parameters if name not in definitions]
        if unknown_params and not action_info.allow_extra_parameters:
            _log("warning", f"Parámetros desconocidos para {action_name}: {unknown_params}", function="validate_action")
>>>>>>> 8d6d091 (correccion pull)
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
<<<<<<< HEAD
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
=======
                    f"{param_name}: recibido {type(value).__name__}, esperado {_format_type_name(expected_type)}"
                )

        if type_errors:
            _log("warning", f"Errores de tipo en {action_name}: {type_errors}", function="validate_action")
            return False
>>>>>>> 8d6d091 (correccion pull)
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
<<<<<<< HEAD
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
=======
        if action_info is None or action_info.function is None:
            return False
        if not self.validate_action(action_name, parameters):
>>>>>>> 8d6d091 (correccion pull)
            return False
        if check_preconditions and state is not None:
<<<<<<< HEAD
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
=======
            return action_info.matches_preconditions(state)
        return True
>>>>>>> 8d6d091 (correccion pull)

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
<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)

        self._record_execution(True)
        self._record_prediction(prediction_memory, action_name, True)
        return result

    def list_actions(self, category: Optional[str] = None) -> List[str]:
        with self._lock:
            if category:
<<<<<<< HEAD
                return [
                    name
                    for name in self.categories.get(category, [])
                    if name in self.actions
                ]
=======
                return [name for name in self.categories.get(category, []) if name in self.actions]
>>>>>>> 8d6d091 (correccion pull)
            return list(self.actions.keys())

    def get_action_categories(self) -> List[str]:
        with self._lock:
            return list(self.categories.keys())

    def get_optimization_stats(self) -> Dict[str, Any]:
<<<<<<< HEAD
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
=======
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
>>>>>>> 8d6d091 (correccion pull)


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
