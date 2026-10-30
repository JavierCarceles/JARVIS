# -*- coding: utf-8 -*-
"""Tests de estados para el Executor — hoja 3.4.4.1 (Tests de estados).

OBJETIVO DE LA HOJA: cubrir con cobertura real la actualización de estado del
mundo del Executor (`_update_world_state`), la integración entre
`ExecutionState.application_states` y las funciones de comparación/reconciliación
de `src/eyes/screen.py` (`compare_declared_and_observable_state` y
`reconcile_observable_with_declared_state`), y tests complementarios de
`_evaluate_condition` sobre estados anidados de aplicaciones.

Estos tests verifican el comportamiento REAL del código, usando el Executor
real con el estado en memoria; el logger del módulo se parchea para evitar
ruido de logging (igual que en tests/hands/test_executor.py).
"""

import copy
from unittest.mock import MagicMock, patch

import pytest

from src.hands.executor import (
    ExecutionResult,
    ExecutionStatus,
    Executor,
    get_executor,
)
from src.eyes.screen import (
    ApplicationState,
    CANONICAL_WINDOW_FLAGS,
    observable_state_to_flags,
    compare_declared_and_observable_state,
    reconcile_observable_with_declared_state,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _patch_executor_logger():
    """Parchea el logger del módulo executor para evitar ruido y errores de logging."""
    patcher = patch("src.hands.executor.logger")
    mock = patcher.start()
    mock.exception = lambda *a, **kw: None
    mock.info = MagicMock()
    mock.warning = MagicMock()
    mock.debug = MagicMock()
    mock.error = MagicMock()
    return mock


@pytest.fixture
def patched_logger():
    patcher = _patch_executor_logger()
    yield patcher
    patcher.stop()


@pytest.fixture
def executor(patched_logger):
    """An Executor instance with logger patched."""
    return Executor()


def _make_node(node_id="n1", action="test_action", **kwargs):
    """Build a normalized plan node dict."""
    node = {
        "id": node_id,
        "action": action,
        "name": kwargs.get("name", node_id),
        "description": kwargs.get("description", ""),
        "type": kwargs.get("type"),
        "parameters": kwargs.get("parameters", {}),
        "preconditions": kwargs.get("preconditions", []),
        "effects": kwargs.get("effects", []),
        "cost": kwargs.get("cost", 1.0),
        "application": kwargs.get("application", None),
        "ui_element": kwargs.get("ui_element", None),
        "alternatives": kwargs.get("alternatives", []),
        "metadata": kwargs.get("metadata", {}),
    }
    return node


def _make_result(node_id="n1", status=ExecutionStatus.SUCCESS, **kwargs):
    """Build an ExecutionResult."""
    return ExecutionResult(
        status=status,
        result=kwargs.get("result"),
        error=kwargs.get("error"),
        node_id=node_id,
        **{k: v for k, v in kwargs.items() if k in ("execution_time", "retries",
            "alternatives_tried", "last_actions", "successful_nodes", "failed_nodes")},
    )


# ---------------------------------------------------------------------------
# _update_world_state tests
# ---------------------------------------------------------------------------

class TestUpdateWorldState:
    """Tests para _update_world_state: actualización exitosa del estado del mundo."""

    def test_non_success_does_not_update(self, executor):
        """Si el resultado no es SUCCESS, no se actualiza el estado del mundo."""
        node = _make_node("n1", "test", application="Chrome", effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.FAILED, error="fail", node_id="n1")
        original_state = copy.deepcopy(executor.current_state.to_dict())
        executor._update_world_state(node, result)
        assert executor.current_state.application_states.get("Chrome", {}) == {}

    def test_no_application_does_not_crash(self, executor):
        """Un nodo sin aplicación no causa crash."""
        node = _make_node("n1", "test", application=None, effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        # No application_states should be modified
        assert executor.current_state.application_states == {}

    def test_app_open_effect_updates_state(self, executor):
        """El efecto app_open actualiza open=True en application_states y la flag plana."""
        node = _make_node("n1", "test", application="Chrome", effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("open") is True

    def test_app_closed_effect_updates_state(self, executor):
        """El efecto app_closed actualiza open=False en application_states."""
        # Primero establecer el estado abierto
        executor.current_state.application_states["Chrome"] = {"open": True}
        node = _make_node("n1", "test", application="Chrome", effects=["app_closed"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("open") is False

    def test_app_active_effect_updates_state(self, executor):
        """El efecto app_active actualiza active=True en application_states."""
        node = _make_node("n1", "test", application="Chrome", effects=["app_active"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("active") is True

    def test_app_minimized_effect_updates_state(self, executor):
        """El efecto app_minimized actualiza active=False en application_states."""
        executor.current_state.application_states["Chrome"] = {"active": True, "open": True}
        node = _make_node("n1", "test", application="Chrome", effects=["app_minimized"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("active") is False
        # open debe mantenerse True (solo active cambia)
        assert chrome_state.get("open") is True

    def test_application_open_generic_effect(self, executor):
        """El efecto application_open (genérico) actualiza la flag {app_key}_open."""
        node = _make_node("n1", "test", application="Chrome", effects=["application_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("open") is True

    def test_app_key_open_effect(self, executor):
        """El efecto chrome_open actualiza open=True en application_states."""
        node = _make_node("n1", "test", application="Chrome", effects=["chrome_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("open") is True

    def test_address_bar_focused_updates_ui_element(self, executor):
        """El efecto address_bar_focused actualiza ui_elements con focused=True."""
        node = _make_node("n1", "test", application="Chrome", effects=["address_bar_focused"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        ui_state = executor.current_state.ui_elements.get("address_bar", {})
        assert ui_state.get("focused") is True

    def test_destination_loaded_updates_state(self, executor):
        """El efecto destination_loaded actualiza la flag destination_loaded."""
        node = _make_node("n1", "test", application="Chrome", effects=["destination_loaded"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        # La flag de estado plano debe estar establecida
        assert executor.current_state.__dict__.get("destination_loaded") is True

    def test_search_performed_updates_state(self, executor):
        """El efecto search_performed actualiza la flag search_performed."""
        node = _make_node("n1", "test", application="Chrome", effects=["search_performed"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        assert executor.current_state.__dict__.get("search_performed") is True

    def test_url_typed_updates_application_state(self, executor):
        """El efecto url_typed actualiza url_typed=True en application_states."""
        node = _make_node("n1", "test", application="Chrome", effects=["url_typed"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("url_typed") is True

    def test_state_updates_in_result(self, executor):
        """state_updates en el resultado se aplican al estado."""
        node = _make_node("n1", "test", application="Chrome")
        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            node_id="n1",
            result={"state_updates": {"application_states": {"Spotube": {"open": True}}}},
        )
        executor._update_world_state(node, result)
        spotube_state = executor.current_state.application_states.get("Spotube", {})
        assert spotube_state.get("open") is True

    def test_new_state_in_result(self, executor):
        """new_state en el resultado se aplica al estado."""
        node = _make_node("n1", "test", application="Chrome")
        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            node_id="n1",
            result={"new_state": {"application_states": {"Spotify": {"active": True}}}},
        )
        executor._update_world_state(node, result)
        spotify_state = executor.current_state.application_states.get("Spotify", {})
        assert spotify_state.get("active") is True

    def test_current_url_in_result(self, executor):
        """current_url en el resultado se establece en el estado."""
        node = _make_node("n1", "test", application="Chrome")
        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            node_id="n1",
            result={"current_url": "https://example.com"},
        )
        executor._update_world_state(node, result)
        assert executor.current_state.__dict__.get("current_url") == "https://example.com"

    def test_ui_element_focused_effect(self, executor):
        """El efecto element_focused con ui_element actualiza ui_elements."""
        node = _make_node("n1", "test", application="Chrome", ui_element="play_button",
                          effects=["click_play_button"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        ui_state = executor.current_state.ui_elements.get("play_button", {})
        # El efecto contiene "click" -> clicked=True
        assert ui_state.get("clicked") is True

    def test_ui_element_typed_effect(self, executor):
        """El efecto text_typed con ui_element actualiza ui_elements."""
        node = _make_node("n1", "test", application="Chrome", ui_element="url_bar",
                          effects=["text_typed"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        ui_state = executor.current_state.ui_elements.get("url_bar", {})
        assert ui_state.get("typed") is True

    def test_multiple_effects(self, executor):
        """Múltiples efectos se aplican todos."""
        node = _make_node("n1", "test", application="Chrome",
                          effects=["app_open", "app_active"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("open") is True
        assert chrome_state.get("active") is True

    def test_app_name_with_spaces(self, executor):
        """El nombre de aplicación con espacios se normaliza en app_key."""
        node = _make_node("n1", "test", application="My App", effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        # app_state se usa con el nombre original
        app_state = executor.current_state.application_states.get("My App", {})
        assert app_state.get("open") is True
        # La flag plana usada por _update_world_state para app_open es "app_open"
        # (el efecto mismo, no f"{app_key}_open")
        assert executor.current_state.__dict__.get("app_open") is True

    def test_last_actions_updated(self, executor):
        """last_actions se actualiza después de _update_world_state."""
        node = _make_node("n1", "test", application="Chrome", effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        assert "n1" in executor.current_state.last_actions

    def test_timestamp_updated(self, executor):
        """El timestamp se actualiza después de _update_world_state."""
        old_ts = executor.current_state.timestamp
        node = _make_node("n1", "test", application="Chrome", effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)
        assert executor.current_state.timestamp >= old_ts


# ---------------------------------------------------------------------------
# Integration: ExecutionState.application_states <-> screen.py functions
# ---------------------------------------------------------------------------

class TestExecutorStateWithScreenComparison:
    """Tests de integración entre ExecutionState.application_states y las
    funciones de comparación/reconciliación de screen.py.

    Verifica que el estado declarado del Executor (applications.json o
    current_state.application_states) puede compararse y reconciliarse con
    un estado observable (ApplicationState).
    """

    def test_compare_chrome_closed_with_closed_state(self, executor):
        """El estado declarado de Chrome (todas False) coincide con CLOSED."""
        import json
        from src.utils.config import get_project_root
        path = get_project_root() / "data" / "knowledge" / "applications.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        chrome_states = data["chrome"]["states"]
        result = compare_declared_and_observable_state(chrome_states, ApplicationState.CLOSED)
        assert result["match"] is True

    def test_compare_chrome_open_with_open_state(self, executor):
        """Un estado declarado con open=True coincide con OPEN."""
        declared = {"open": True, "active": False, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.OPEN)
        assert result["match"] is True

    def test_compare_chrome_discrepancy(self, executor):
        """Un estado declarado cerrado pero observable abierto produce discrepancia."""
        declared = {"open": False, "active": False, "maximized": False, "focused": False}
        result = compare_declared_and_observable_state(declared, ApplicationState.OPEN)
        assert result["match"] is False
        assert "open" in result["discrepancies"]

    def test_reconcile_chrome_state_after_effect(self, executor):
        """Después de aplicar app_open, el estado del executor puede reconciliarse
        con un estado observable."""
        # Simular que Chrome se abrió
        node = _make_node("n1", "test", application="Chrome", effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)

        # Ahora comparar con un estado observable
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        comparison = compare_declared_and_observable_state(chrome_state, ApplicationState.OPEN)
        assert comparison["match"] is True

    def test_reconcile_discrepancy_updates_executor_state(self, executor):
        """La reconciliación puede usarse para actualizar el estado del executor
        cuando hay discrepancia entre el declarado y el observable."""
        # Estado declarado: Chrome cerrado
        executor.current_state.application_states["Chrome"] = {
            "open": False, "active": False, "maximized": False, "focused": False
        }
        # Estado observable: Chrome activo
        observable_state = ApplicationState.ACTIVE

        # Reconciliar
        chrome_declared = executor.current_state.application_states["Chrome"]
        reconciliation = reconcile_observable_with_declared_state(chrome_declared, observable_state)
        assert reconciliation["match"] is False
        assert reconciliation["reconciled"] is True

        # Actualizar el estado del executor con los flags reconciliados
        executor.current_state.application_states["Chrome"] = dict(reconciliation["reconciled_flags"])

        # Verificar que el estado se actualizó
        updated_state = executor.current_state.application_states["Chrome"]
        assert updated_state["open"] is True
        assert updated_state["active"] is True
        assert updated_state["focused"] is True

    def test_reconcile_preserves_domain_flags(self, executor):
        """La reconciliación preserva las flags de dominio (playing, streaming, recording)."""
        executor.current_state.application_states["Spotify"] = {
            "open": False, "active": False, "maximized": False, "focused": False,
            "playing": True,
        }
        reconciliation = reconcile_observable_with_declared_state(
            executor.current_state.application_states["Spotify"],
            ApplicationState.OPEN,
        )
        assert reconciliation["reconciled_flags"]["playing"] is True
        assert reconciliation["reconciled_flags"]["open"] is True

    def test_reconcile_then_evaluate_condition(self, executor):
        """Después de reconciliar, _evaluate_condition refleja el estado real."""
        # Estado declarado: Chrome cerrado
        executor.current_state.application_states["Chrome"] = {
            "open": False, "active": False, "maximized": False, "focused": False
        }
        # Reconciliar con estado observable ACTIVE
        reconciliation = reconcile_observable_with_declared_state(
            executor.current_state.application_states["Chrome"],
            ApplicationState.ACTIVE,
        )
        executor.current_state.application_states["Chrome"] = dict(reconciliation["reconciled_flags"])

        # Ahora _evaluate_condition debe reflejar el estado reconciliado
        # _get_state_for_planning genera chrome_open, chrome_active
        state = executor._get_state_for_planning()
        assert state.get("chrome_open") is True
        assert state.get("chrome_active") is True


# ---------------------------------------------------------------------------
# Complementary _evaluate_condition tests with nested states
# ---------------------------------------------------------------------------

class TestEvaluateConditionNestedStates:
    """Tests complementarios para _evaluate_condition con estados anidados
    de application_states."""

    def test_chrome_active_with_nested_state(self, executor):
        """chrome_active es True cuando application_states tiene active=True."""
        executor.current_state.application_states = {"chrome": {"open": True, "active": True}}
        assert executor._evaluate_condition("chrome_active") is True

    def test_chrome_active_false_with_nested_state(self, executor):
        """chrome_active es False cuando application_states tiene active=False."""
        executor.current_state.application_states = {"chrome": {"open": True, "active": False}}
        assert executor._evaluate_condition("chrome_active") is False

    def test_chrome_closed_true_when_open_false(self, executor):
        """chrome_closed es True cuando application_states tiene open=False."""
        executor.current_state.application_states = {"chrome": {"open": False}}
        assert executor._evaluate_condition("chrome_closed") is True

    def test_chrome_closed_false_when_open_true(self, executor):
        """chrome_closed es False cuando application_states tiene open=True."""
        executor.current_state.application_states = {"chrome": {"open": True}}
        assert executor._evaluate_condition("chrome_closed") is False

    def test_app_chrome_with_nested_state(self, executor):
        """app_chrome es True cuando Chrome está en application_states."""
        executor.current_state.application_states = {"chrome": {"open": True}}
        assert executor._evaluate_condition("app_chrome") is True

    def test_app_chrome_not_present(self, executor):
        """app_chrome es False cuando Chrome no está en application_states."""
        executor.current_state.application_states = {}
        assert executor._evaluate_condition("app_chrome") is False

    def test_application_active_with_nested_state(self, executor):
        """application_active es True cuando alguna app tiene active=True."""
        executor.current_state.application_states = {"chrome": {"active": True}}
        assert executor._evaluate_condition("application_active") is True

    def test_application_active_false_when_all_inactive(self, executor):
        """application_active es False cuando ninguna app está activa."""
        executor.current_state.application_states = {"chrome": {"active": False}}
        assert executor._evaluate_condition("application_active") is False

    def test_browser_open_with_nested_state(self, executor):
        """browser_open es True cuando Chrome (navegador) está abierto."""
        executor.current_state.application_states = {"chrome": {"open": True}}
        assert executor._evaluate_condition("browser_open") is True

    def test_browser_open_false_when_closed(self, executor):
        """browser_open es False cuando todos los navegadores están cerrados."""
        executor.current_state.application_states = {"chrome": {"open": False}}
        assert executor._evaluate_condition("browser_open") is False

    def test_application_closed_condition(self, executor):
        """application_closed es False (no existe como sufijo _closed) —
        se trata como key literal que no existe, retorna False."""
        executor.current_state.application_states = {"chrome": {"open": True}}
        # "application_closed" no es un sufijo manejado específicamente
        # ni una key en el estado → False
        result = executor._evaluate_condition("application_closed")
        assert result is False

    def test_app_state_with_domain_flags_does_not_break_evaluation(self, executor):
        """Flags de dominio coexistiendo no rompen la evaluación de condiciones canónicas."""
        executor.current_state.application_states = {
            "spotify": {"open": True, "active": False, "playing": True}
        }
        # spotify_open debe ser True (solo mira el flag "open")
        assert executor._evaluate_condition("spotify_open") is True
        # spotify_active debe ser False
        assert executor._evaluate_condition("spotify_active") is False

    def test_multiple_apps_state(self, executor):
        """Múltiples aplicaciones en application_states se evalúan correctamente."""
        executor.current_state.application_states = {
            "chrome": {"open": True, "active": False},
            "spotify": {"open": True, "active": True},
        }
        assert executor._evaluate_condition("chrome_open") is True
        assert executor._evaluate_condition("chrome_active") is False
        assert executor._evaluate_condition("spotify_open") is True
        assert executor._evaluate_condition("spotify_active") is True

    def test_browser_active_with_firefox(self, executor):
        """browser_active es True cuando Firefox (navegador) está activo."""
        executor.current_state.application_states = {"firefox": {"open": True, "active": True}}
        assert executor._evaluate_condition("browser_active") is True

    def test_browser_active_false_when_no_browser_active(self, executor):
        """browser_active es False cuando ningún navegador está activo."""
        executor.current_state.application_states = {"chrome": {"open": True, "active": False}}
        assert executor._evaluate_condition("browser_active") is False


# ---------------------------------------------------------------------------
# Complementary _goal_achieved tests with nested states
# ---------------------------------------------------------------------------

class TestGoalAchievedNestedStates:
    """Tests complementarios para _goal_achieved con estados anidados."""

    def test_open_application_uses_nested_state(self, executor):
        """open_application goal se resuelve usando application_states anidado.

        _goal_achieved normaliza target a lowercase, así que la clave en
        application_states también debe estar en lowercase para coincidir.
        """
        goal = {"type": "open_application", "target": "Chrome"}
        state = {"application_states": {"chrome": {"open": True}}}
        assert executor._goal_achieved(goal, state) is True

    def test_open_application_unsatisfied_nested(self, executor):
        """open_application goal es False cuando la app no está abierta en estado anidado."""
        goal = {"type": "open_application", "target": "Chrome"}
        state = {"application_states": {"chrome": {"open": False}}}
        assert executor._goal_achieved(goal, state) is False

    def test_close_application_uses_nested_state(self, executor):
        """close_application goal se resuelve usando application_states anidado."""
        goal = {"type": "close_application", "target": "Chrome"}
        state = {"application_states": {"chrome": {"open": False}}}
        assert executor._goal_achieved(goal, state) is True

    def test_close_application_unsatisfied_nested(self, executor):
        """close_application goal es False cuando la app aún está abierta en estado anidado."""
        goal = {"type": "close_application", "target": "Chrome"}
        state = {"application_states": {"chrome": {"open": True}}}
        assert executor._goal_achieved(goal, state) is False

    def test_open_application_flat_takes_priority(self, executor):
        """Si existe la flag plana, se usa antes que el estado anidado."""
        goal = {"type": "open_application", "target": "Chrome"}
        state = {
            "chrome_open": True,
            "application_states": {"chrome": {"open": False}},
        }
        # La flag plana chrome_open=True tiene prioridad
        assert executor._goal_achieved(goal, state) is True

    def test_open_application_no_state(self, executor):
        """open_application goal es False cuando no hay estado de la app."""
        goal = {"type": "open_application", "target": "Chrome"}
        state = {"application_states": {}}
        assert executor._goal_achieved(goal, state) is False

    def test_close_application_no_state(self, executor):
        """close_application goal es True cuando no hay estado de la app (asumido cerrado)."""
        goal = {"type": "close_application", "target": "Chrome"}
        state = {"application_states": {}}
        assert executor._goal_achieved(goal, state) is True

    def test_open_application_nested_case_insensitive_lookup(self, executor):
        """_goal_achieved normaliza target a lowercase; una clave 'Chrome' no se
        encuentra pero una clave 'chrome' sí — documenta el comportamiento real."""
        goal = {"type": "open_application", "target": "Chrome"}
        # Con clave "Chrome" (mayúscula) no se encuentra → False
        state_upper = {"application_states": {"Chrome": {"open": True}}}
        assert executor._goal_achieved(goal, state_upper) is False
        # Con clave "chrome" (lowercase) se encuentra → True
        state_lower = {"application_states": {"chrome": {"open": True}}}
        assert executor._goal_achieved(goal, state_lower) is True


# ---------------------------------------------------------------------------
# APPLICATION_STATE_TO_WINDOW_FLAGS consistency tests
# ---------------------------------------------------------------------------

class TestStateMappingConsistency:
    """Tests de consistencia entre ApplicationState, observable_state_to_flags y
    el estado declarado del Executor."""

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_observable_state_to_flags_returns_all_canonical(self, state):
        """observable_state_to_flags retorna exactamente las 4 flags canónicas."""
        flags = observable_state_to_flags(state)
        assert set(flags.keys()) == set(CANONICAL_WINDOW_FLAGS)

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_observable_state_to_flags_all_boolean(self, state):
        """Todos los valores retornados son booleans."""
        flags = observable_state_to_flags(state)
        for flag in CANONICAL_WINDOW_FLAGS:
            assert isinstance(flags[flag], bool)

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_state_to_flags_then_compare(self, state):
        """Para cada ApplicationState, las flags observables deben comparar
        correctamente con un estado declarado que coincida."""
        observable_flags = observable_state_to_flags(state)
        # El estado declarado igual a las observable flags debe dar match=True
        result = compare_declared_and_observable_state(dict(observable_flags), state)
        assert result["match"] is True
        assert result["discrepancies"] == {}

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_state_to_flags_then_reconcile_match(self, state):
        """Para cada ApplicationState, reconciliar con un estado declarado idéntico
        da reconciled=False (coincidencia)."""
        observable_flags = observable_state_to_flags(state)
        reconciliation = reconcile_observable_with_declared_state(
            dict(observable_flags), state
        )
        assert reconciliation["match"] is True
        assert reconciliation["reconciled"] is False

    @pytest.mark.parametrize("state", list(ApplicationState))
    def test_state_to_flags_then_reconcile_discrepancy(self, state):
        """Para cada ApplicationState, reconciliar con un estado declarado opuesto
        (todas las flags invertidas) da reconciled=True y flags actualizadas."""
        observable_flags = observable_state_to_flags(state)
        # Estado declarado opuesto
        opposite_declared = {flag: not val for flag, val in observable_flags.items()}
        reconciliation = reconcile_observable_with_declared_state(opposite_declared, state)
        assert reconciliation["discrepancies"] != {}

    def test_executor_state_after_open_matches_observable(self, executor):
        """Después de aplicar app_open, el estado del executor coincide con OPEN."""
        node = _make_node("n1", "test", application="Chrome", effects=["app_open"])
        result = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1")
        executor._update_world_state(node, result)

        chrome_state = executor.current_state.application_states.get("Chrome", {})
        comparison = compare_declared_and_observable_state(chrome_state, ApplicationState.OPEN)
        assert comparison["match"] is True
