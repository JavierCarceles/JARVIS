"""Tipos base para el sistema de precondiciones y efectos.

Evita importaciones circulares con ``action_registry`` y mantiene un contrato
común para la evaluación de condiciones y la aplicación de efectos sobre el
estado utilizado por el grafo y el planificador.

Las condiciones inválidas fallan de forma segura. Los efectos devuelven un
estado nuevo y no modifican el estado de entrada.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any, Callable, Dict, List, Optional, Set

from src.utils.logger import get_logger

logger = get_logger(__name__)


State = Dict[str, Any]
ConditionFunction = Callable[[State], bool]
EffectFunction = Callable[[State, Dict[str, Any]], State]

_MAX_COMPOSITE_DEPTH = 64


class ConditionType(Enum):
    """Tipos de condiciones de precondición/efecto."""

    STATE_EQUALS = "state_equals"
    STATE_EXISTS = "state_exists"
    STATE_TRUE = "state_true"
    STATE_GREATER_THAN = "state_greater_than"
    STATE_LESS_THAN = "state_less_than"
    APPLICATION_OPEN = "application_open"
    APPLICATION_ACTIVE = "application_active"
    UI_ELEMENT_AVAILABLE = "ui_element_available"
    UI_ELEMENT_CALIBRATED = "ui_element_calibrated"
    CUSTOM_FUNCTION = "custom_function"
    COMPOSITE_AND = "composite_and"
    COMPOSITE_OR = "composite_or"


def _safe_copy(value: Any, memo: Optional[Dict[int, Any]] = None) -> Any:
    """Copia valores comunes de forma defensiva, tolerando objetos no copiables.

    ``deepcopy`` conserva normalmente la topología de objetos y los ciclos. Si
    un objeto personalizado impide copiar el contenedor completo, se intenta
    copiar recursivamente sus elementos; el último recurso para un objeto
    opaco es conservar la referencia en lugar de hacer fallar todo el estado.
    """
    if memo is None:
        memo = {}

    value_id = id(value)
    if value_id in memo:
        return memo[value_id]

    if isinstance(value, dict):
        result: Dict[Any, Any] = {}
        memo[value_id] = result
        for key, item in value.items():
            try:
                copied_key = _safe_copy(key, memo)
                copied_item = _safe_copy(item, memo)
                result[copied_key] = copied_item
            except Exception:
                try:
                    result[key] = item
                except Exception:
                    continue
        return result

    if isinstance(value, list):
        result_list: List[Any] = []
        memo[value_id] = result_list
        result_list.extend(_safe_copy(item, memo) for item in value)
        return result_list

    if isinstance(value, set):
        result_set: Set[Any] = set()
        memo[value_id] = result_set
        for item in value:
            try:
                result_set.add(_safe_copy(item, memo))
            except Exception:
                try:
                    result_set.add(item)
                except Exception:
                    continue
        return result_set

    if isinstance(value, tuple):
        # Tuplas ordinarias no suelen contener ciclos mutables directos; el
        # intento de deepcopy conserva correctamente los casos soportados.
        try:
            result_tuple = deepcopy(value, memo)
            memo[value_id] = result_tuple
            return result_tuple
        except Exception:
            try:
                result_tuple = tuple(_safe_copy(item, memo) for item in value)
                memo[value_id] = result_tuple
                return result_tuple
            except Exception:
                return value

    try:
        result = deepcopy(value, memo)
        memo[value_id] = result
        return result
    except Exception:
        return value


def _normalize_name(value: Any) -> str:
    """Normaliza nombres usados como claves de estado."""
    if value is None:
        return ""
    return str(value).strip().lower()


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _safe_number(value: Any) -> Optional[float]:
    """Convierte a float únicamente valores numéricos finitos."""
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _as_bool(value: Any) -> bool:
    """Interpreta flags comunes sin tratar la cadena ``'false'`` como cierta."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        number = _safe_number(value)
        return bool(number) if number is not None else False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {
            "",
            "0",
            "false",
            "no",
            "off",
            "closed",
            "inactive",
            "none",
            "null",
        }:
            return False
        if normalized in {"1", "true", "yes", "on", "open", "active", "running"}:
            return True
    return bool(value)


def _get_nested_state_value(
    state: State,
    key: Optional[str],
    default: Any = None,
) -> Any:
    """Obtiene una clave directa o una ruta sencilla separada por puntos."""
    if key is None:
        return default
    try:
        if key in state:
            return state[key]
    except (TypeError, KeyError):
        return default

    path = str(key)
    if not path:
        return default

    current: Any = state
    for part in path.split("."):
        if not _is_mapping(current) or part not in current:
            return default
        current = current[part]
    return current


def _get_application_state(state: State, app_name: Any) -> Dict[str, Any]:
    """Busca el estado de una aplicación en varios formatos compatibles."""
    name = str(app_name or "").strip()
    normalized = _normalize_name(name)
    if not normalized:
        return {}

    for container_name in ("applications", "application_states"):
        container = state.get(container_name)
        if not _is_mapping(container):
            continue

        for candidate in (name, normalized):
            value = container.get(candidate)
            if _is_mapping(value):
                return value

        for key, value in container.items():
            if _normalize_name(key) == normalized and _is_mapping(value):
                return value

    return {}


def _get_boolean_application_flag(
    state: State,
    app_name: Any,
    flag: str,
) -> bool:
    """Obtiene un flag de aplicación desde estado plano o anidado."""
    normalized_app = _normalize_name(app_name)
    if not normalized_app:
        return False

    app_state = _get_application_state(state, app_name)
    if flag in app_state:
        return _as_bool(app_state.get(flag))

    state_label = str(app_state.get("state", "")).strip().lower()
    if flag == "open" and state_label in {"open", "opened", "active", "running"}:
        return True
    if flag == "active" and state_label in {"active", "foreground"}:
        return True

    candidates = (
        f"{normalized_app}_{flag}",
        f"app_{normalized_app}_{flag}",
        f"{normalized_app}.{flag}",
    )
    return any(_as_bool(state.get(key, False)) for key in candidates)


def _get_ui_element_state(
    state: State,
    app_name: Any,
    element_name: Any,
) -> Dict[str, Any]:
    """Busca el estado de un elemento UI sin confundir aplicaciones distintas."""
    app = str(app_name or "").strip()
    element = str(element_name or "").strip()
    normalized_app = _normalize_name(app)
    normalized_element = _normalize_name(element)
    if not normalized_element:
        return {}

    ui_elements = state.get("ui_elements")
    if not _is_mapping(ui_elements):
        return {}

    # Formato anidado: {app: {elemento: {...}}}.
    if normalized_app:
        app_bucket: Optional[Dict[str, Any]] = None
        for key, value in ui_elements.items():
            if _normalize_name(key) == normalized_app and _is_mapping(value):
                app_bucket = value
                break

        if app_bucket is not None:
            for key, value in app_bucket.items():
                if _normalize_name(key) == normalized_element and _is_mapping(value):
                    return value
            # Si la aplicación está presente pero ese elemento no, no se debe
            # aceptar por error un elemento homónimo de otra aplicación.
            return {}

        # Formatos planos compuestos con la aplicación incluida en la clave.
        for key in (
            f"{normalized_app}_{normalized_element}",
            f"{normalized_app}.{normalized_element}",
        ):
            value = ui_elements.get(key)
            if _is_mapping(value):
                return value

    # Formato plano legado: {elemento: {available: ..., calibrated: ...}}.
    for key, value in ui_elements.items():
        if _normalize_name(key) == normalized_element and _is_mapping(value):
            # No interpretar como elemento una carpeta de otra aplicación.
            if any(
                prop in value
                for prop in ("available", "calibrated", "focused", "visible")
            ):
                return value

    return {}


def _resolve_condition_type(value: Any) -> ConditionType:
    """Convierte un enum, valor textual o alias histórico a ``ConditionType``.

    Los tipos desconocidos se rechazan en vez de convertirse silenciosamente
    en ``STATE_TRUE``, ya que esa conversión podría autorizar una acción por
    error.
    """
    if isinstance(value, ConditionType):
        return value

    normalized = str(value or "").strip().lower()
    aliases = {
        "state": ConditionType.STATE_EQUALS,
        "equals": ConditionType.STATE_EQUALS,
        "equal": ConditionType.STATE_EQUALS,
        "true": ConditionType.STATE_TRUE,
        "functional": ConditionType.CUSTOM_FUNCTION,
        "custom": ConditionType.CUSTOM_FUNCTION,
        "function": ConditionType.CUSTOM_FUNCTION,
    }
    if normalized in aliases:
        return aliases[normalized]

    for condition_type in ConditionType:
        if condition_type.value == normalized:
            return condition_type

    raise ValueError(f"Tipo de condición no soportado: {value!r}")


@dataclass
class Condition:
    """Representa una condición que debe cumplirse para ejecutar una acción."""

    type: ConditionType
    key: Optional[str] = None
    expected_value: Any = None
    function: Optional[ConditionFunction] = None
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

    def evaluate(self, state: State) -> bool:
        """Evalúa la condición contra el estado actual sin mutarlo."""
        return self._evaluate(state, set(), 0)

    def _evaluate(
        self,
        state: State,
        active_conditions: Set[int],
        depth: int,
    ) -> bool:
        if not isinstance(state, dict) or depth > _MAX_COMPOSITE_DEPTH:
            return False

        condition_id = id(self)
        if condition_id in active_conditions:
            return False

        try:
            condition_type = _resolve_condition_type(self.type)
        except (TypeError, ValueError):
            return False

        try:
            if condition_type == ConditionType.STATE_EQUALS:
                sentinel = object()
                actual = _get_nested_state_value(state, self.key, sentinel)
                return actual is not sentinel and actual == self.expected_value

            if condition_type == ConditionType.STATE_EXISTS:
                sentinel = object()
                return (
                    _get_nested_state_value(state, self.key, sentinel) is not sentinel
                )

            if condition_type == ConditionType.STATE_TRUE:
                return _as_bool(_get_nested_state_value(state, self.key, False))

            if condition_type in {
                ConditionType.STATE_GREATER_THAN,
                ConditionType.STATE_LESS_THAN,
            }:
                current = _safe_number(_get_nested_state_value(state, self.key, None))
                expected = _safe_number(self.expected_value)
                if current is None or expected is None:
                    return False
                if condition_type == ConditionType.STATE_GREATER_THAN:
                    return current > expected
                return current < expected

            if condition_type == ConditionType.APPLICATION_OPEN:
                app_name = self.parameters.get("app_name") or self.parameters.get(
                    "application"
                )
                if app_name:
                    return _get_boolean_application_flag(state, app_name, "open")
                if self.key:
                    direct_value = _get_nested_state_value(state, self.key, None)
                    if direct_value is not None:
                        return _as_bool(direct_value)
                derived = str(self.key or "")
                if derived.endswith("_open"):
                    derived = derived[:-5]
                return _get_boolean_application_flag(state, derived, "open")

            if condition_type == ConditionType.APPLICATION_ACTIVE:
                app_name = self.parameters.get("app_name") or self.parameters.get(
                    "application"
                )
                if app_name:
                    return _get_boolean_application_flag(state, app_name, "active")
                if self.key:
                    direct_value = _get_nested_state_value(state, self.key, None)
                    if direct_value is not None:
                        return _as_bool(direct_value)
                derived = str(self.key or "")
                if derived.endswith("_active"):
                    derived = derived[:-7]
                return _get_boolean_application_flag(state, derived, "active")

            if condition_type in {
                ConditionType.UI_ELEMENT_AVAILABLE,
                ConditionType.UI_ELEMENT_CALIBRATED,
            }:
                app_name = self.parameters.get("app_name") or self.parameters.get(
                    "application"
                )
                element_name = self.parameters.get("element_name") or self.key
                ui_state = _get_ui_element_state(state, app_name, element_name)
                property_name = (
                    "available"
                    if condition_type == ConditionType.UI_ELEMENT_AVAILABLE
                    else "calibrated"
                )
                if property_name in ui_state:
                    return _as_bool(ui_state.get(property_name))

                normalized_app = _normalize_name(app_name)
                normalized_element = _normalize_name(element_name)
                suffix_key = f"{normalized_app}_{normalized_element}_{property_name}"
                legacy_key = f"ui_{normalized_app}_{normalized_element}_{property_name}"
                return _as_bool(state.get(suffix_key, False)) or _as_bool(
                    state.get(legacy_key, False)
                )

            if condition_type == ConditionType.CUSTOM_FUNCTION:
                if not callable(self.function):
                    return False
                # Evita que una función de condición cambie el estado del plan.
                return bool(self.function(_safe_copy(state)))

            if condition_type in {
                ConditionType.COMPOSITE_AND,
                ConditionType.COMPOSITE_OR,
            }:
                sub_conditions = self.parameters.get("conditions", [])
                if not isinstance(sub_conditions, (list, tuple)):
                    return False
                active_conditions.add(condition_id)
                try:
                    evaluated = (
                        _coerce_condition(item)._evaluate(
                            state, active_conditions, depth + 1
                        )
                        for item in sub_conditions
                    )
                    return (
                        all(evaluated)
                        if condition_type == ConditionType.COMPOSITE_AND
                        else any(evaluated)
                    )
                finally:
                    active_conditions.discard(condition_id)

            return False
        except Exception:
            # Una condición inválida nunca debe habilitar una acción.
            return False


@dataclass
class Effect:
    """Representa un efecto que modifica el estado tras ejecutar una acción."""

    type: str
    key: str
    value: Any = None
    function: Optional[EffectFunction] = None
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    cumulative: bool = False

    def apply(
        self,
        state: State,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> State:
        """Aplica el efecto y devuelve un estado nuevo sin mutar la entrada."""
        if not isinstance(state, dict):
            return {}
        original = _safe_copy(state)
        result = execution_result if isinstance(execution_result, dict) else {}
        try:
            return self._apply_internal(
                original,
                result,
                active_effects=set(),
                depth=0,
            )
        except Exception as exc:
            try:
                logger.warning(
                    "No se pudo aplicar el efecto %s sobre %r: %s",
                    self.type,
                    self.key,
                    exc,
                )
            except Exception:
                pass
            return _safe_copy(state)

    def _apply_internal(
        self,
        state: State,
        execution_result: Dict[str, Any],
        active_effects: Set[int],
        depth: int,
    ) -> State:
        if depth > _MAX_COMPOSITE_DEPTH:
            return state

        effect_id = id(self)
        effect_type = str(self.type or "state_set").strip().lower()
        key = str(self.key or "").strip()
        result_state = _safe_copy(state)

        if effect_type == "state_set":
            if not key:
                return result_state
            result_state[key] = _safe_copy(self.value)
            return result_state

        if effect_type in {"state_increment", "state_decrement"}:
            if not key:
                return result_state
            current_raw = result_state.get(key, 0)
            current_number = _safe_number(current_raw)
            delta = _safe_number(self.value if self.value is not None else 1)
            if current_number is None or delta is None:
                return result_state
            new_value = (
                current_number + delta
                if effect_type == "state_increment"
                else current_number - delta
            )
            if not isfinite(new_value):
                return result_state
            if (
                isinstance(current_raw, int)
                and not isinstance(current_raw, bool)
                and new_value.is_integer()
            ):
                result_state[key] = int(new_value)
            else:
                result_state[key] = new_value
            return result_state

        if effect_type == "state_append":
            if not key:
                return result_state
            current_list = result_state.get(key, [])
            if not isinstance(current_list, list):
                current_list = []
            current_list.append(_safe_copy(self.value))
            result_state[key] = current_list
            return result_state

        if effect_type == "state_remove":
            if not key:
                return result_state
            current_list = result_state.get(key, [])
            if isinstance(current_list, list):
                result_state[key] = [
                    item for item in current_list if item != self.value
                ]
            return result_state

        if effect_type in {
            "application_open",
            "application_close",
            "application_activate",
        }:
            app_name = (
                self.parameters.get("app_name")
                or self.parameters.get("application")
                or key
            )
            normalized_app = _normalize_name(app_name)
            if not normalized_app:
                return result_state

            if effect_type == "application_open":
                changes = {"open": True, "active": True}
            elif effect_type == "application_close":
                changes = {"open": False, "active": False}
            else:
                changes = {"active": True}

            for flag, value in changes.items():
                result_state[f"{normalized_app}_{flag}"] = value
            _update_application_state(result_state, app_name, changes)
            return result_state

        if effect_type in {"ui_element_calibrate", "ui_element_focus"}:
            app_name = self.parameters.get("app_name") or self.parameters.get(
                "application"
            )
            element_name = self.parameters.get("element_name") or key
            normalized_app = _normalize_name(app_name)
            normalized_element = _normalize_name(element_name)
            if not normalized_element:
                return result_state

            if effect_type == "ui_element_calibrate":
                changes = {"calibrated": True, "available": True}
                properties = ("calibrated", "available")
            else:
                changes = {"focused": True}
                properties = ("focused",)

            for property_name in properties:
                result_state[
                    f"{normalized_app}_{normalized_element}_{property_name}"
                ] = True
            _update_ui_element_state(result_state, app_name, element_name, changes)
            return result_state

        if effect_type == "custom_function":
            if not callable(self.function):
                return result_state
            # La función opera sobre una copia transaccional. Solo se acepta el
            # estado retornado si es un diccionario; mutaciones externas del
            # resultado de ejecución no se propagan.
            transformed = self.function(
                _safe_copy(result_state), _safe_copy(execution_result)
            )
            return (
                _safe_copy(transformed)
                if isinstance(transformed, dict)
                else result_state
            )

        if effect_type == "composite":
            if effect_id in active_effects:
                return result_state
            sub_effects = self.parameters.get("effects", [])
            if not isinstance(sub_effects, (list, tuple)):
                return result_state
            active_effects.add(effect_id)
            try:
                for item in sub_effects:
                    sub_effect = _coerce_effect(item)
                    if id(sub_effect) in active_effects:
                        continue
                    result_state = sub_effect._apply_internal(
                        result_state,
                        execution_result,
                        active_effects,
                        depth + 1,
                    )
            finally:
                active_effects.discard(effect_id)
            return result_state

        # Tipos de efecto desconocidos no deben mutar el estado.
        return result_state


def _coerce_condition(value: Any) -> Condition:
    """Convierte una condición soportada a ``Condition`` de forma segura."""
    if isinstance(value, Condition):
        return value

    if isinstance(value, dict):
        parameters = value.get("parameters", {})
        if not isinstance(parameters, dict):
            parameters = {}

        raw_type = value.get("type", ConditionType.STATE_TRUE.value)
        try:
            condition_type = _resolve_condition_type(raw_type)
        except (TypeError, ValueError):
            condition_type = ConditionType.CUSTOM_FUNCTION
            function: Optional[ConditionFunction] = lambda _: False
        else:
            candidate = value.get("function")
            function = candidate if callable(candidate) else None

        return Condition(
            type=condition_type,
            key=value.get("key"),
            expected_value=value.get("value", value.get("expected_value")),
            function=function,
            description=str(value.get("description", "") or ""),
            parameters=parameters,
        )

    if isinstance(value, str):
        return Condition(type=ConditionType.STATE_TRUE, key=value)

    return Condition(
        type=ConditionType.CUSTOM_FUNCTION,
        function=lambda _: False,
    )


def _coerce_effect(value: Any) -> Effect:
    """Convierte un efecto soportado a ``Effect``."""
    if isinstance(value, Effect):
        return value

    if isinstance(value, dict):
        parameters = value.get("parameters", {})
        if not isinstance(parameters, dict):
            parameters = {}

        key = value.get("key", value.get("state", ""))
        function_candidate = value.get("function")
        return Effect(
            type=str(value.get("type", "state_set") or "state_set"),
            key=str(key or ""),
            value=value.get("value"),
            function=function_candidate if callable(function_candidate) else None,
            description=str(value.get("description", "") or ""),
            parameters=parameters,
            cumulative=bool(value.get("cumulative", False)),
        )

    if isinstance(value, str):
        return Effect(type="state_set", key=value, value=True)

    return Effect(type="state_set", key="", value=None)


def _update_application_state(
    state: State,
    app_name: Any,
    changes: Dict[str, Any],
) -> None:
    """Actualiza, cuando existe, el formato anidado ``applications``."""
    applications = state.get("applications")
    if not isinstance(applications, dict) or not app_name:
        return

    normalized = _normalize_name(app_name)
    target = next(
        (
            value
            for key, value in applications.items()
            if _normalize_name(key) == normalized and isinstance(value, dict)
        ),
        None,
    )
    if isinstance(target, dict):
        target.update(_safe_copy(changes))


def _update_ui_element_state(
    state: State,
    app_name: Any,
    element_name: Any,
    changes: Dict[str, Any],
) -> None:
    """Actualiza, cuando existe, el formato ``ui_elements`` compatible."""
    ui_elements = state.get("ui_elements")
    if not isinstance(ui_elements, dict) or not element_name:
        return

    normalized_app = _normalize_name(app_name)
    normalized_element = _normalize_name(element_name)

    # Formato {app: {elemento: {...}}}.
    if normalized_app:
        for app_key, app_bucket in ui_elements.items():
            if _normalize_name(app_key) != normalized_app or not isinstance(
                app_bucket, dict
            ):
                continue
            for element_key, value in app_bucket.items():
                if _normalize_name(element_key) == normalized_element and isinstance(
                    value, dict
                ):
                    value.update(_safe_copy(changes))
                    return
            # No añadir un elemento inexistente ni actualizar otro del mismo nombre.
            return

    # Formato plano {elemento: {...}}.
    for element_key, value in ui_elements.items():
        if (
            _normalize_name(element_key) == normalized_element
            and isinstance(value, dict)
            and any(
                prop in value
                for prop in ("available", "calibrated", "focused", "visible")
            )
        ):
            value.update(_safe_copy(changes))
            return


__all__ = [
    "ConditionType",
    "Condition",
    "Effect",
    "State",
    "ConditionFunction",
    "EffectFunction",
]
