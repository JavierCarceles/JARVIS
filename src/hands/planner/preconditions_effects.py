"""
Sistema avanzado de precondiciones y efectos para planificación jerárquica.

Responsabilidades:
- Construcción y reutilización de condiciones y efectos.
- Evaluación de precondiciones simples, compuestas y funcionales.
- Aplicación determinista y acumulativa de efectos sobre estados.
- Integración con ActionInfo/ActionType del registro central de acciones.
- Utilidades comunes para acciones de aplicaciones y elementos UI.

El modelo canónico de Condition/Effect se mantiene en
``preconditions_effects_types``; este módulo actúa como gestor y adaptador.
"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any, Callable, Dict, List, Optional, Union

from src.hands.action_registry import ActionInfo, ActionType
from src.hands.planner.preconditions_effects_types import (
    Condition,
    ConditionType,
    Effect,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

State = Dict[str, Any]
ConditionInput = Union[str, Dict[str, Any], Condition, Callable[[State], bool]]
EffectInput = Union[
    str, Dict[str, Any], Effect, Callable[[State, Dict[str, Any]], State]
]


def _safe_copy(value: Any, memo: Optional[Dict[int, Any]] = None) -> Any:
    """Copia datos incluyendo contenedores cíclicos y valores no copiables."""
    try:
        return deepcopy(value)
    except Exception:
        if memo is None:
            memo = {}
        identity = id(value)
        if identity in memo:
            return memo[identity]

        if isinstance(value, dict):
            copied: Dict[Any, Any] = {}
            memo[identity] = copied
            for key, item in value.items():
                copied[_safe_copy(key, memo)] = _safe_copy(item, memo)
            return copied
        if isinstance(value, list):
            copied_list: List[Any] = []
            memo[identity] = copied_list
            copied_list.extend(_safe_copy(item, memo) for item in value)
            return copied_list
        if isinstance(value, set):
            copied_set: set = set()
            memo[identity] = copied_set
            for item in value:
                try:
                    copied_set.add(_safe_copy(item, memo))
                except Exception:
                    copied_set.add(item)
            return copied_set
        if isinstance(value, tuple):
            # Un marcador evita recursión infinita en tuplas que participan en
            # ciclos indirectos a través de listas/diccionarios.
            memo[identity] = value
            try:
                copied_tuple = tuple(_safe_copy(item, memo) for item in value)
                memo[identity] = copied_tuple
                return copied_tuple
            except Exception:
                return value
        return value


def _safe_state_copy(state: Any) -> State:
    """Devuelve una copia independiente del estado recibido."""
    if not isinstance(state, dict):
        return {}
    copied = _safe_copy(state)
    return copied if isinstance(copied, dict) else dict(state)


class PreconditionsEffectsManager:
    """Gestor centralizado de precondiciones y efectos."""

    def __init__(self) -> None:
        self.conditions: Dict[str, Condition] = {}
        self.effects: Dict[str, Effect] = {}
        self.condition_templates: Dict[ConditionType, Dict[str, Any]] = {}
        self.effect_templates: Dict[str, Dict[str, Any]] = {}
        self._initialize_templates()
        logger.info(
            "[PRECONDITIONS-EFFECTS] Sistema de precondiciones y efectos inicializado"
        )

    def _initialize_templates(self) -> None:
        """Inicializa plantillas comunes de condiciones y efectos."""
        templates: Dict[ConditionType, Dict[str, Any]] = {}

        for name, description, parameters in (
            ("STATE_EQUALS", "Estado igual a valor", {"expected_value": "valor"}),
            ("STATE_TRUE", "Estado es verdadero", {}),
            ("APPLICATION_OPEN", "Aplicación abierta", {"app_name": "nombre_app"}),
            ("APPLICATION_ACTIVE", "Aplicación activa", {"app_name": "nombre_app"}),
            (
                "UI_ELEMENT_AVAILABLE",
                "Elemento UI disponible",
                {"app_name": "nombre_app", "element_name": "nombre_elemento"},
            ),
            (
                "UI_ELEMENT_CALIBRATED",
                "Elemento UI calibrado",
                {"app_name": "nombre_app", "element_name": "nombre_elemento"},
            ),
        ):
            condition_type = getattr(ConditionType, name, None)
            if condition_type is not None:
                templates[condition_type] = {
                    "description": description,
                    "parameters": parameters,
                }

        self.condition_templates = templates
        self.effect_templates = {
            "application_open": {
                "description": "Abrir aplicación",
                "type": "application_open",
                "parameters": {"app_name": "nombre_app"},
            },
            "ui_element_calibrate": {
                "description": "Calibrar elemento UI",
                "type": "ui_element_calibrate",
                "parameters": {
                    "app_name": "nombre_app",
                    "element_name": "nombre_elemento",
                },
            },
            "state_increment": {
                "description": "Incrementar estado numérico",
                "type": "state_increment",
                "parameters": {"increment": 1},
            },
        }

    def create_condition(
        self,
        condition_type: ConditionType,
        key: Optional[str] = None,
        expected_value: Any = None,
        function: Optional[Callable[[State], bool]] = None,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Condition:
        """Crea una condición y la registra para reutilización."""
        condition_type = self._resolve_condition_type(condition_type)
        condition = Condition(
            type=condition_type,
            key=key,
            expected_value=expected_value,
            function=function,
            description=description or f"Condición {condition_type.value}",
            parameters=dict(parameters or {}),
        )

        condition_id = self._make_registry_key(condition_type.value, key)
        self.conditions[condition_id] = condition
        return condition

    def create_effect(
        self,
        effect_type: str,
        key: Optional[str],
        value: Any = None,
        function: Optional[Callable[[State, Dict[str, Any]], State]] = None,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        cumulative: bool = False,
    ) -> Effect:
        """Crea un efecto y lo registra para reutilización."""
        normalized_type = (
            str(getattr(effect_type, "value", effect_type)).strip().lower()
        )
        effect = Effect(
            type=normalized_type,
            key=key,
            value=value,
            function=function,
            description=description or f"Efecto {normalized_type}",
            parameters=dict(parameters or {}),
            cumulative=bool(cumulative),
        )

        effect_id = self._make_registry_key(normalized_type, key)
        self.effects[effect_id] = effect
        return effect

    @staticmethod
    def _make_registry_key(kind: Any, key: Any) -> str:
        return f"{getattr(kind, 'value', kind)}_{key or '__root__'}"

    def create_composite_condition(
        self,
        conditions: List[ConditionInput],
        operator: str = "and",
        description: str = "",
    ) -> Condition:
        """Crea una condición compuesta AND u OR."""
        normalized_operator = str(operator).strip().lower()
        if normalized_operator not in {"and", "or"}:
            raise ValueError("operator debe ser 'and' u 'or'")

        condition_type_name = (
            "COMPOSITE_AND" if normalized_operator == "and" else "COMPOSITE_OR"
        )
        condition_type = getattr(ConditionType, condition_type_name, None)
        if condition_type is None:
            raise ValueError(f"ConditionType.{condition_type_name} no está definido")

        normalized_conditions = [self._ensure_condition(item) for item in conditions]
        return Condition(
            type=condition_type,
            key=None,
            description=description or f"Condición compuesta {normalized_operator}",
            parameters={
                "conditions": normalized_conditions,
                "operator": normalized_operator,
            },
        )

    def verify_action_preconditions(
        self, action_info: ActionInfo, current_state: State
    ) -> bool:
        """Devuelve True cuando todas las precondiciones de la acción se cumplen."""
        if action_info is None or not isinstance(current_state, dict):
            return False

        preconditions = self._normalize_sequence(
            getattr(action_info, "preconditions", [])
        )
        functional_preconditions = self._normalize_sequence(
            getattr(action_info, "preconditions_functions", [])
        )
        if not preconditions and not functional_preconditions:
            return True

        try:
            for precondition in preconditions:
                if not self.evaluate_condition(precondition, current_state):
                    logger.debug(
                        "[PRECONDITIONS] Precondición no cumplida para acción: %s",
                        getattr(action_info, "name", "<desconocida>"),
                    )
                    return False

            for precondition_function in functional_preconditions:
                if not callable(precondition_function):
                    logger.warning(
                        "[PRECONDITIONS] Precondición funcional inválida para la acción %s",
                        getattr(action_info, "name", "<desconocida>"),
                    )
                    return False
                if not bool(precondition_function(_safe_state_copy(current_state))):
                    logger.debug(
                        "[PRECONDITIONS] Precondición funcional no cumplida para la acción %s",
                        getattr(action_info, "name", "<desconocida>"),
                    )
                    return False

            return True
        except Exception:
            logger.exception(
                "[PRECONDITIONS] Error verificando precondiciones de la acción %s",
                getattr(action_info, "name", "<desconocida>"),
            )
            return False

    def evaluate_condition(
        self, condition: ConditionInput, current_state: State
    ) -> bool:
        """Evalúa una condición individual o funcional de forma segura."""
        if not isinstance(current_state, dict):
            return False

        try:
            safe_state = _safe_state_copy(current_state)
            if isinstance(condition, Condition):
                evaluator = getattr(condition, "evaluate", None)
                if not callable(evaluator):
                    raise TypeError("Condition no expone evaluate(state)")
                return bool(evaluator(safe_state))

            if callable(condition):
                return bool(condition(safe_state))

            if isinstance(condition, str):
                return bool(safe_state.get(condition, False))

            if isinstance(condition, dict):
                return self._dict_condition_matches(condition, safe_state)

            # No convertir objetos desconocidos a bool: podría habilitar una
            # acción accidentalmente por la mera veracidad de una instancia.
            return False
        except Exception:
            logger.exception("[PRECONDITIONS] Error evaluando condición")
            return False

    def _dict_condition_matches(self, condition: Dict[str, Any], state: State) -> bool:
        if "conditions" in condition:
            operator = (
                str(condition.get("operator", condition.get("op", "and")))
                .strip()
                .lower()
            )
            if operator not in {"and", "or"}:
                return False
            children = condition.get("conditions") or []
            if not isinstance(children, (list, tuple, set)):
                return False
            results = [self.evaluate_condition(child, state) for child in children]
            return all(results) if operator == "and" else any(results)

        if "function" in condition:
            function = condition.get("function")
            return (
                bool(function(_safe_state_copy(state))) if callable(function) else False
            )

        condition_obj = self._dict_to_condition(condition)
        evaluator = getattr(condition_obj, "evaluate", None)
        if callable(evaluator):
            return bool(evaluator(state))

        key = condition.get("key", condition.get("state"))
        if key is None:
            return False
        expected = condition.get(
            "equals",
            condition.get(
                "expected_value",
                condition.get("expected", condition.get("value", True)),
            ),
        )
        return state.get(key) == expected

    def _dict_to_condition(self, condition_dict: Dict[str, Any]) -> Condition:
        raw_type = condition_dict.get("type")
        if raw_type is None:
            # Las funciones y los valores esperados tienen semántica explícita;
            # los diccionarios que solo contienen una clave son booleanos.
            if callable(condition_dict.get("function")):
                raw_type = "custom_function"
            else:
                has_expected_value = any(
                    name in condition_dict
                    for name in ("equals", "expected_value", "expected", "value")
                )
                raw_type = "state_equals" if has_expected_value else "state_true"
        condition_type = self._resolve_condition_type(raw_type)
        key = condition_dict.get("key", condition_dict.get("state"))
        expected_value = condition_dict.get(
            "expected_value",
            condition_dict.get(
                "expected",
                condition_dict.get("equals", condition_dict.get("value")),
            ),
        )
        description = condition_dict.get("description", "")
        raw_parameters = condition_dict.get("parameters") or {}
        parameters = dict(raw_parameters) if isinstance(raw_parameters, dict) else {}
        function = condition_dict.get("function")
        if "conditions" in condition_dict:
            children = condition_dict.get("conditions") or []
            if not isinstance(children, (list, tuple)):
                raise ValueError("Las condiciones compuestas deben contener una lista")
            operator = (
                str(condition_dict.get("operator", condition_dict.get("op", "and")))
                .strip()
                .lower()
            )
            if operator not in {"and", "or"}:
                raise ValueError("Operador compuesto no válido")
            parameters["conditions"] = [
                self._ensure_condition(item) for item in children
            ]
            condition_type = (
                ConditionType.COMPOSITE_AND
                if operator == "and"
                else ConditionType.COMPOSITE_OR
            )

        return Condition(
            type=condition_type,
            key=key,
            expected_value=expected_value,
            function=function if callable(function) else None,
            description=description,
            parameters=parameters,
        )

    def _resolve_condition_type(self, raw_type: Any) -> ConditionType:
        if isinstance(raw_type, ConditionType):
            return raw_type

        normalized = str(getattr(raw_type, "value", raw_type)).strip().lower()

        aliases = {
            "state": ConditionType.STATE_TRUE,
            "true": ConditionType.STATE_TRUE,
            "equals": ConditionType.STATE_EQUALS,
            "equal": ConditionType.STATE_EQUALS,
            "functional": getattr(ConditionType, "CUSTOM_FUNCTION", None),
            "custom": getattr(ConditionType, "CUSTOM_FUNCTION", None),
            "function": getattr(ConditionType, "CUSTOM_FUNCTION", None),
        }

        aliased = aliases.get(normalized)
        if aliased is not None:
            return aliased

        try:
            return ConditionType(normalized)
        except ValueError:
            member_name = normalized.upper()
            try:
                value = getattr(ConditionType, member_name)
            except AttributeError as exc:
                raise ValueError(f"Tipo de condición desconocido: {raw_type}") from exc
            if not isinstance(value, ConditionType):
                raise ValueError(f"Tipo de condición desconocido: {raw_type}")
            return value

    def apply_action_effects(
        self,
        action_info: ActionInfo,
        current_state: State,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> State:
        """Aplica los efectos de la acción y devuelve un nuevo estado."""
        original_state = _safe_state_copy(current_state)
        state = _safe_state_copy(original_state)
        if action_info is None:
            return state

        effects = self._normalize_sequence(getattr(action_info, "effects", []))
        effect_functions = self._normalize_sequence(
            getattr(action_info, "effects_functions", [])
        )
        if not effects and not effect_functions:
            return state

        result = _safe_state_copy(execution_result)

        try:
            for effect in effects:
                state = self.apply_effect(effect, state, result)

            for effect_function in effect_functions:
                if not callable(effect_function):
                    raise TypeError("Un efecto funcional registrado no es invocable")
                updated_state = effect_function(
                    _safe_state_copy(state), _safe_state_copy(result)
                )
                if not isinstance(updated_state, dict):
                    raise TypeError("Un efecto funcional debe devolver dict de estado")
                state = _safe_state_copy(updated_state)

            return state
        except Exception:
            logger.exception(
                "[PRECONDITIONS] Error aplicando efectos de la acción %s",
                getattr(action_info, "name", "<desconocida>"),
            )
            # Contrato transaccional: si un efecto falla, no devolver un estado
            # intermedio que parezca parcialmente aplicado.
            return original_state

    def apply_effect(
        self,
        effect: EffectInput,
        current_state: State,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> State:
        """Aplica un efecto individual."""
        state = _safe_state_copy(current_state)
        result = _safe_state_copy(execution_result)

        if isinstance(effect, Effect):
            applier = getattr(effect, "apply", None)
            if not callable(applier):
                raise TypeError("Effect no expone apply(state, execution_result)")
            updated = applier(_safe_state_copy(state), _safe_state_copy(result))
            if not isinstance(updated, dict):
                raise TypeError("Effect.apply debe devolver dict de estado")
            return updated

        if callable(effect):
            updated = effect(_safe_state_copy(state), _safe_state_copy(result))
            if not isinstance(updated, dict):
                raise TypeError("Un efecto funcional debe devolver dict de estado")
            return updated

        if isinstance(effect, str):
            effect_obj = Effect(
                type="state_set",
                key=effect,
                value=True,
                description=f"Efecto: {effect}",
            )
            return self.apply_effect(effect_obj, state, result)

        if isinstance(effect, dict):
            if callable(effect.get("function")):
                return self.apply_effect(effect["function"], state, result)
            effect_obj = self._dict_to_effect(effect)
            return self.apply_effect(effect_obj, state, result)

        raise TypeError(f"Efecto no soportado: {type(effect).__name__}")

    def _dict_to_effect(self, effect_dict: Dict[str, Any]) -> Effect:
        effect_type = effect_dict.get("type", "state_set")
        key = effect_dict.get("key", effect_dict.get("state"))
        value = effect_dict.get("value")
        description = effect_dict.get("description", "")
        raw_parameters = effect_dict.get("parameters") or {}
        parameters = dict(raw_parameters) if isinstance(raw_parameters, dict) else {}
        cumulative = bool(effect_dict.get("cumulative", False))
        function = effect_dict.get("function")

        return Effect(
            type=str(getattr(effect_type, "value", effect_type)).strip().lower(),
            key=key,
            value=value,
            function=function if callable(function) else None,
            description=description,
            parameters=parameters,
            cumulative=cumulative,
        )

    def get_state_requirements_for_action(
        self, action_info: ActionInfo
    ) -> Dict[str, Any]:
        """Extrae solo precondiciones representables como requisitos escalares.

        Las condiciones compuestas, funcionales y numéricas (> / <) se omiten:
        convertirlas a una igualdad o a un booleano alteraría su semántica.
        """
        requirements: Dict[str, Any] = {}
        if action_info is None:
            return requirements

        for precondition in self._normalize_sequence(
            getattr(action_info, "preconditions", [])
        ):
            if isinstance(precondition, Condition):
                try:
                    condition_type = self._resolve_condition_type(
                        getattr(precondition, "type", None)
                    )
                except (TypeError, ValueError):
                    continue

                key = getattr(precondition, "key", None)
                parameters = getattr(precondition, "parameters", {}) or {}
                if not isinstance(parameters, dict):
                    parameters = {}

                if condition_type == ConditionType.STATE_TRUE and key:
                    requirements[key] = True
                elif condition_type == ConditionType.STATE_EQUALS and key:
                    requirements[key] = getattr(precondition, "expected_value", None)
                elif condition_type == ConditionType.APPLICATION_OPEN:
                    app_name = (
                        parameters.get("app_name")
                        or parameters.get("application")
                        or key
                    )
                    normalized_app = str(app_name or "").strip().lower()
                    if normalized_app:
                        requirements[f"{normalized_app}_open"] = True
                elif condition_type == ConditionType.APPLICATION_ACTIVE:
                    app_name = (
                        parameters.get("app_name")
                        or parameters.get("application")
                        or key
                    )
                    normalized_app = str(app_name or "").strip().lower()
                    if normalized_app:
                        requirements[f"{normalized_app}_active"] = True
                elif condition_type in {
                    ConditionType.UI_ELEMENT_AVAILABLE,
                    ConditionType.UI_ELEMENT_CALIBRATED,
                }:
                    app_name = parameters.get("app_name") or parameters.get(
                        "application"
                    )
                    element_name = parameters.get("element_name") or key
                    normalized_element = str(element_name or "").strip().lower()
                    if normalized_element:
                        normalized_app = str(app_name or "").strip().lower()
                        prefix = (
                            f"{normalized_app}_{normalized_element}_"
                            if normalized_app
                            else f"{normalized_element}_"
                        )
                        suffix = (
                            "available"
                            if condition_type == ConditionType.UI_ELEMENT_AVAILABLE
                            else "calibrated"
                        )
                        requirements[f"{prefix}{suffix}"] = True
                continue

            if isinstance(precondition, dict):
                try:
                    condition_type = self._resolve_condition_type(
                        precondition.get("type", "state_true")
                    )
                except (TypeError, ValueError):
                    continue

                key = precondition.get("key", precondition.get("state"))
                if condition_type == ConditionType.STATE_TRUE and key:
                    requirements[key] = True
                elif condition_type == ConditionType.STATE_EQUALS and key:
                    requirements[key] = precondition.get(
                        "expected_value",
                        precondition.get(
                            "expected",
                            precondition.get("equals", precondition.get("value")),
                        ),
                    )
                elif condition_type in {
                    ConditionType.APPLICATION_OPEN,
                    ConditionType.APPLICATION_ACTIVE,
                }:
                    parameters = precondition.get("parameters") or {}
                    if not isinstance(parameters, dict):
                        parameters = {}
                    app_name = (
                        parameters.get("app_name")
                        or parameters.get("application")
                        or key
                    )
                    normalized_app = str(app_name or "").strip().lower()
                    if normalized_app:
                        suffix = (
                            "open"
                            if condition_type == ConditionType.APPLICATION_OPEN
                            else "active"
                        )
                        requirements[f"{normalized_app}_{suffix}"] = True
                elif condition_type in {
                    ConditionType.UI_ELEMENT_AVAILABLE,
                    ConditionType.UI_ELEMENT_CALIBRATED,
                }:
                    parameters = precondition.get("parameters") or {}
                    if not isinstance(parameters, dict):
                        parameters = {}
                    app_name = parameters.get("app_name") or parameters.get(
                        "application"
                    )
                    element_name = parameters.get("element_name") or key
                    normalized_element = str(element_name or "").strip().lower()
                    if normalized_element:
                        normalized_app = str(app_name or "").strip().lower()
                        prefix = (
                            f"{normalized_app}_{normalized_element}_"
                            if normalized_app
                            else f"{normalized_element}_"
                        )
                        suffix = (
                            "available"
                            if condition_type == ConditionType.UI_ELEMENT_AVAILABLE
                            else "calibrated"
                        )
                        requirements[f"{prefix}{suffix}"] = True
            elif isinstance(precondition, str):
                requirements[precondition] = True

        return requirements

    def get_state_modifications_from_action(
        self, action_info: ActionInfo
    ) -> Dict[str, Any]:
        """Extrae modificaciones de estado estáticas de los efectos."""
        modifications: Dict[str, Any] = {}
        if action_info is None:
            return modifications

        for effect in self._normalize_sequence(getattr(action_info, "effects", [])):
            if isinstance(effect, Effect):
                effect_type = (
                    str(getattr(getattr(effect, "type", ""), "value", effect.type))
                    .strip()
                    .lower()
                )
                key = getattr(effect, "key", None)
                value = getattr(effect, "value", True)
                parameters = getattr(effect, "parameters", {}) or {}

                if effect_type == "application_open":
                    app_name = parameters.get("app_name") or key
                    normalized_app = str(app_name or "").strip().lower()
                    if normalized_app:
                        modifications[f"{normalized_app}_open"] = True
                        modifications[f"{normalized_app}_active"] = True
                    elif key:
                        modifications[key] = True
                    continue

                if effect_type == "application_close":
                    app_name = parameters.get("app_name") or key
                    normalized_app = str(app_name or "").strip().lower()
                    if normalized_app:
                        modifications[f"{normalized_app}_open"] = False
                        modifications[f"{normalized_app}_active"] = False
                    elif key:
                        modifications[key] = False
                    continue

                if effect_type == "application_activate":
                    app_name = parameters.get("app_name") or key
                    normalized_app = str(app_name or "").strip().lower()
                    if normalized_app:
                        modifications[f"{normalized_app}_active"] = True
                    elif key:
                        modifications[key] = True
                    continue

                if effect_type == "ui_element_calibrate":
                    app_name = parameters.get("app_name") or parameters.get(
                        "application"
                    )
                    element_name = parameters.get("element_name") or key
                    normalized_app = str(app_name or "").strip().lower()
                    normalized_element = str(element_name or "").strip().lower()
                    if normalized_element:
                        prefix = (
                            f"{normalized_app}_{normalized_element}_"
                            if normalized_app
                            else f"{normalized_element}_"
                        )
                        modifications[f"{prefix}calibrated"] = True
                        modifications[f"{prefix}available"] = True
                    continue

                if effect_type == "ui_element_focus":
                    app_name = parameters.get("app_name") or parameters.get(
                        "application"
                    )
                    element_name = parameters.get("element_name") or key
                    normalized_app = str(app_name or "").strip().lower()
                    normalized_element = str(element_name or "").strip().lower()
                    if normalized_element:
                        prefix = (
                            f"{normalized_app}_{normalized_element}_"
                            if normalized_app
                            else f"{normalized_element}_"
                        )
                        modifications[f"{prefix}focused"] = True
                    continue

                # Los efectos incrementales, de lista o funcionales no tienen
                # un valor final deducible sin conocer el estado de entrada.
                if effect_type == "state_set" and key:
                    modifications[key] = value
                continue

            if isinstance(effect, dict):
                state_key = effect.get("state", effect.get("key"))
                if state_key is not None:
                    effect_type = str(effect.get("type", "state_set")).strip().lower()
                    if effect_type == "application_open":
                        app_name = (effect.get("parameters") or {}).get(
                            "app_name"
                        ) or state_key
                        normalized_app = str(app_name).strip().lower()
                        modifications[f"{normalized_app}_open"] = True
                        modifications[f"{normalized_app}_active"] = True
                    elif effect_type == "application_close":
                        app_name = (effect.get("parameters") or {}).get(
                            "app_name"
                        ) or state_key
                        normalized_app = str(app_name).strip().lower()
                        modifications[f"{normalized_app}_open"] = False
                        modifications[f"{normalized_app}_active"] = False
                    elif effect_type == "application_activate":
                        app_name = (effect.get("parameters") or {}).get(
                            "app_name"
                        ) or state_key
                        normalized_app = str(app_name).strip().lower()
                        modifications[f"{normalized_app}_active"] = True
                    elif effect_type == "ui_element_calibrate":
                        parameters = effect.get("parameters") or {}
                        app_name = parameters.get("app_name") or parameters.get(
                            "application"
                        )
                        element_name = parameters.get("element_name") or state_key
                        normalized_app = str(app_name or "").strip().lower()
                        normalized_element = str(element_name or "").strip().lower()
                        if normalized_element:
                            prefix = (
                                f"{normalized_app}_{normalized_element}_"
                                if normalized_app
                                else f"{normalized_element}_"
                            )
                            modifications[f"{prefix}calibrated"] = True
                            modifications[f"{prefix}available"] = True
                    elif effect_type == "ui_element_focus":
                        parameters = effect.get("parameters") or {}
                        app_name = parameters.get("app_name") or parameters.get(
                            "application"
                        )
                        element_name = parameters.get("element_name") or state_key
                        normalized_app = str(app_name or "").strip().lower()
                        normalized_element = str(element_name or "").strip().lower()
                        if normalized_element:
                            prefix = (
                                f"{normalized_app}_{normalized_element}_"
                                if normalized_app
                                else f"{normalized_element}_"
                            )
                            modifications[f"{prefix}focused"] = True
                    elif effect_type == "state_set":
                        modifications[state_key] = effect.get("value", True)
            elif isinstance(effect, str):
                modifications[effect] = True

        return modifications

    def create_action_with_preconditions_effects(
        self,
        name: str,
        description: str,
        preconditions: List[ConditionInput],
        effects: List[EffectInput],
        cost: float = 1.0,
        **kwargs: Any,
    ) -> ActionInfo:
        """Crea un ActionInfo compatible con el registro central de acciones."""
        try:
            normalized_cost = float(cost)
        except (TypeError, ValueError) as exc:
            raise ValueError("El coste de una acción debe ser numérico") from exc
        if not isfinite(normalized_cost) or normalized_cost < 0:
            raise ValueError("El coste de una acción debe ser finito y no negativo")

        confidence_threshold = kwargs.get("confidence_threshold", 0.8)
        try:
            confidence_threshold = float(confidence_threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence_threshold debe estar entre 0 y 1") from exc
        if not isfinite(confidence_threshold) or not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold debe estar entre 0 y 1")

        action_type = kwargs.get("action_type", ActionType.APPLICATION)
        if isinstance(action_type, str):
            action_type = self._resolve_action_type(action_type)

        action_info = ActionInfo(
            name=name,
            description=description,
            action_type=action_type,
            function=kwargs.get("function"),
            parameters=dict(kwargs.get("parameters") or {}),
            module=kwargs.get("module", "preconditions_effects"),
            category=kwargs.get("category", "general"),
            tags=self._normalize_sequence(kwargs.get("tags", [])),
            confidence_threshold=confidence_threshold,
            preconditions=self._normalize_sequence(preconditions),
            effects=self._normalize_sequence(effects),
            cost=normalized_cost,
            dependencies=self._normalize_sequence(kwargs.get("dependencies", [])),
            capability=kwargs.get("capability"),
            application=kwargs.get("application"),
            required_resources=self._normalize_sequence(
                kwargs.get("required_resources", [])
            ),
            requires_ui_element=kwargs.get("requires_ui_element"),
            success_checker=kwargs.get("success_checker"),
            planner_enabled=bool(kwargs.get("planner_enabled", True)),
            preconditions_functions=self._normalize_sequence(
                kwargs.get("preconditions_functions", [])
            ),
            effects_functions=self._normalize_sequence(
                kwargs.get("effects_functions", [])
            ),
        )

        logger.info(
            "[PRECONDITIONS-EFFECTS] Acción creada con precondiciones/efectos: %s",
            name,
        )
        return action_info

    @staticmethod
    def _normalize_sequence(value: Any) -> List[Any]:
        """Normaliza una colección sin alterar el orden de listas y tuplas."""
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, set):
            return sorted(value, key=lambda item: (type(item).__name__, repr(item)))
        return [value]

    def _ensure_condition(self, condition: ConditionInput) -> Condition:
        if isinstance(condition, Condition):
            return condition
        if isinstance(condition, dict):
            if "conditions" in condition:
                children = condition.get("conditions") or []
                if not isinstance(children, (list, tuple)):
                    raise TypeError(
                        "Las condiciones compuestas deben ser una lista o tupla"
                    )
                operator = (
                    str(condition.get("operator", condition.get("op", "and")))
                    .strip()
                    .lower()
                )
                return self.create_composite_condition(
                    list(children),
                    operator=operator,
                    description=str(condition.get("description", "")),
                )
            return self._dict_to_condition(condition)
        if isinstance(condition, str):
            return Condition(
                type=self._resolve_condition_type("state_true"),
                key=condition,
                description=f"Precondición: {condition}",
            )
        if callable(condition):
            function_type = getattr(ConditionType, "CUSTOM_FUNCTION", None)
            if function_type is None:
                raise ValueError("ConditionType.CUSTOM_FUNCTION no está definido")
            return Condition(
                type=function_type,
                function=condition,
                description="Precondición funcional",
            )
        raise TypeError(f"Condición no soportada: {type(condition).__name__}")

    @staticmethod
    def _resolve_action_type(raw_type: str) -> ActionType:
        normalized = str(getattr(raw_type, "value", raw_type)).strip().lower()
        for action_type in ActionType:
            if (
                action_type.value == normalized
                or action_type.name.lower() == normalized
            ):
                return action_type
        raise ValueError(f"ActionType desconocido: {raw_type}")


_preconditions_effects_manager: Optional[PreconditionsEffectsManager] = None


def get_preconditions_effects_manager() -> PreconditionsEffectsManager:
    """Obtiene la instancia global del gestor."""
    global _preconditions_effects_manager
    if _preconditions_effects_manager is None:
        _preconditions_effects_manager = PreconditionsEffectsManager()
    return _preconditions_effects_manager


def create_application_open_condition(app_name: str) -> Condition:
    """Crea una condición que representa una aplicación abierta."""
    manager = get_preconditions_effects_manager()
    condition_type = getattr(ConditionType, "APPLICATION_OPEN", None)
    if condition_type is None:
        condition_type = ConditionType.STATE_EQUALS
        return manager.create_condition(
            condition_type=condition_type,
            key=f"{app_name.lower()}_open",
            expected_value=True,
            parameters={"app_name": app_name},
            description=f"Aplicación {app_name} abierta",
        )

    return manager.create_condition(
        condition_type=condition_type,
        key=f"{app_name.lower()}_open",
        parameters={"app_name": app_name},
        description=f"Aplicación {app_name} abierta",
    )


def create_application_active_condition(app_name: str) -> Condition:
    """Crea una condición que representa una aplicación activa."""
    manager = get_preconditions_effects_manager()
    condition_type = getattr(ConditionType, "APPLICATION_ACTIVE", None)
    if condition_type is None:
        condition_type = ConditionType.STATE_EQUALS
        return manager.create_condition(
            condition_type=condition_type,
            key=f"{app_name.lower()}_active",
            expected_value=True,
            parameters={"app_name": app_name},
            description=f"Aplicación {app_name} activa",
        )

    return manager.create_condition(
        condition_type=condition_type,
        key=f"{app_name.lower()}_active",
        parameters={"app_name": app_name},
        description=f"Aplicación {app_name} activa",
    )


def create_ui_element_calibrated_condition(
    app_name: str, element_name: str
) -> Condition:
    """Crea una condición que representa un elemento UI calibrado."""
    manager = get_preconditions_effects_manager()
    condition_type = getattr(ConditionType, "UI_ELEMENT_CALIBRATED", None)
    if condition_type is None:
        condition_type = ConditionType.STATE_EQUALS
        return manager.create_condition(
            condition_type=condition_type,
            key=f"{app_name.lower()}_{element_name}_calibrated",
            expected_value=True,
            parameters={"app_name": app_name, "element_name": element_name},
            description=f"Elemento {element_name} de {app_name} calibrado",
        )

    return manager.create_condition(
        condition_type=condition_type,
        key=f"{app_name.lower()}_{element_name}_calibrated",
        parameters={"app_name": app_name, "element_name": element_name},
        description=f"Elemento {element_name} de {app_name} calibrado",
    )


def create_application_open_effect(app_name: str) -> Effect:
    """Crea un efecto que representa una aplicación abierta."""
    manager = get_preconditions_effects_manager()
    return manager.create_effect(
        effect_type="application_open",
        key=f"{app_name.lower()}_open",
        value=True,
        parameters={"app_name": app_name},
        description=f"Aplicación {app_name} abierta",
    )


def create_ui_element_calibrate_effect(app_name: str, element_name: str) -> Effect:
    """Crea un efecto que representa un elemento UI calibrado."""
    manager = get_preconditions_effects_manager()
    return manager.create_effect(
        effect_type="ui_element_calibrate",
        key=f"{app_name.lower()}_{element_name}_calibrated",
        value=True,
        parameters={"app_name": app_name, "element_name": element_name},
        description=f"Elemento {element_name} de {app_name} calibrado",
    )


__all__ = [
    "PreconditionsEffectsManager",
    "get_preconditions_effects_manager",
    "create_application_open_condition",
    "create_application_active_condition",
    "create_ui_element_calibrated_condition",
    "create_application_open_effect",
    "create_ui_element_calibrate_effect",
]
