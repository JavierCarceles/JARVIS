# -*- coding: utf-8 -*-
"""Tests de verificación de la hoja 3.3.3.2 — "Verificar que Planner no recibe
acciones inexistentes".

El planificador debe disponer de un mecanismo para **verificar** (no eliminar)
que las acciones de un plan existen en el ``ActionRegistry``.  La verificación
se expone en la metadata del ``PlanningResult`` (``action_verification``) y como
advertencias, sin romper planes que contienen nodos legacy/UI que el executor
resuelve por otros medios.

Métodos bajo prueba:

* ``Planner.action_exists(action_name)``
* ``Planner._resolve_node_action_name(node)`` (estático)
* ``Planner.validate_plan_actions(plan)``
* ``Planner.filter_existing_actions(plan)``
* Integración en ``_create_plan`` (``action_verification`` en metadata)
* Integración en ``build_application_aware_plan``

Se ejerce contra el modelo REAL: el ``ActionRegistry`` global registrado durante
la importación de ``src.hands``.
"""

import logging
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# SUPRESIÓN DE LOG DE SISTEMA (antes de importar src/)
# ---------------------------------------------------------------------------
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from src.hands.planner.planner import (  # noqa: E402
    Planner,
    PlannerStatus,
)
from src.hands.planner.node import Goal  # noqa: E402

# ---------------------------------------------------------------------------
# Acciones realmente registradas en el ActionRegistry global
# ---------------------------------------------------------------------------
REGISTERED_ACTIONS = {
    "open_application",
    "close_application",
    "type_text",
    "press_key",
    "click_mouse",
    "move_mouse",
    "scroll_mouse",
    "execute_hotkey",
    "open_start_menu",
    "close_window",
    "switch_window",
    "navigate_enter",
    "navigate_tab",
    "copy_text",
    "cut_text",
    "paste_text",
    "select_all",
    "wait_for_application_state",
    "calibrate_application_ui",
    "calibrate_applications",
    "calibrar_aplicaciones",
    "abrir_chrome",
    "cerrar_chrome",
    "calibrar_chrome",
    "mover_chrome_pantalla",
    "maximizar_chrome",
    "abrir_chrome_pantalla",
}

NONEXISTENT_ACTIONS = {
    "chrome_open",
    "press_enter",
    "type_url",
    "focus_address_bar",
    "chrome.activate",
    "accion_que_no_existe",
}


@pytest.fixture(autouse=True, scope="session")
def _suppress_system_logs():
    logging.disable(logging.CRITICAL)
    yield


def _planner() -> Planner:
    return Planner()


# ---------------------------------------------------------------------------
# action_exists
# ---------------------------------------------------------------------------


class TestActionExists:
    """``action_exists`` verifica la presencia de una acción en el ActionRegistry."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    @pytest.mark.parametrize("action_name", sorted(REGISTERED_ACTIONS))
    def test_registered_action_exists(self, action_name):
        """Todas las acciones registradas reales devuelven True."""
        assert self.planner.action_exists(action_name) is True

    @pytest.mark.parametrize("action_name", sorted(NONEXISTENT_ACTIONS))
    def test_nonexistent_action_does_not_exist(self, action_name):
        """Acciones inexistentes (compatibilidad/UI sin registrar) devuelven False."""
        assert self.planner.action_exists(action_name) is False

    def test_empty_string_returns_false(self):
        assert self.planner.action_exists("") is False

    def test_whitespace_only_returns_false(self):
        assert self.planner.action_exists("   ") is False

    def test_non_string_input_returns_false(self):
        assert self.planner.action_exists(None) is False
        assert self.planner.action_exists(123) is False
        assert self.planner.action_exists([]) is False


# ---------------------------------------------------------------------------
# _resolve_node_action_name
# ---------------------------------------------------------------------------


class TestResolveNodeActionName:
    """``_resolve_node_action_name`` resuelve el nombre de acción efectivo de un
    paso de plan, replicando la lógica del Executor."""

    def test_node_with_action_and_id(self):
        """Cuando ``action`` coincide con ``id``, se usa el nombre del nodo."""
        node = {"id": "press_enter", "action": "press_enter"}
        assert Planner._resolve_node_action_name(node) == "press_enter"

    def test_node_id_as_action(self):
        """Si solo hay ``id``, se usa como nombre de acción."""
        node = {"id": "chrome_open"}
        assert Planner._resolve_node_action_name(node) == "chrome_open"

    def test_node_with_callback_returns_none(self):
        """Un nodo con ``execute_callback`` no necesita registro → None."""
        callback = MagicMock()
        node = {"id": "custom_step", "execute_callback": callback}
        assert Planner._resolve_node_action_name(node) is None

    def test_node_with_metadata_action_name(self):
        """``metadata['action_name']`` se prioriza sobre el ``id`` del nodo."""
        node = {
            "id": "step_1",
            "action": "step_1",
            "metadata": {"action_name": "open_application"},
        }
        assert Planner._resolve_node_action_name(node) == "open_application"

    def test_node_with_metadata_action(self):
        """``metadata['action']`` también se prioriza sobre el ``id`` del nodo."""
        node = {
            "id": "step_1",
            "action": "step_1",
            "metadata": {"action": "type_text"},
        }
        assert Planner._resolve_node_action_name(node) == "type_text"

    def test_node_with_explicit_action_and_id_differ(self):
        """Si ``action`` difiere de ``id`, se prefiere ``action`` (no override)."""
        node = {"id": "step_1", "action": "open_application"}
        assert Planner._resolve_node_action_name(node) == "open_application"

    def test_non_dict_node_returns_none(self):
        assert Planner._resolve_node_action_name("not_a_dict") is None
        assert Planner._resolve_node_action_name(None) is None

    def test_callback_in_metadata_takes_precedence(self):
        """``metadata['execute_callback']`` también invalida la búsqueda."""
        callback = MagicMock()
        node = {
            "id": "step_1",
            "action": "chrome_open",
            "metadata": {"execute_callback": callback},
        }
        assert Planner._resolve_node_action_name(node) is None

    def test_empty_id_returns_none(self):
        """Un nodo sin ``id`` ni ``action`` ni ``action_name`` → None."""
        node = {}
        assert Planner._resolve_node_action_name(node) is None


# ---------------------------------------------------------------------------
# validate_plan_actions
# ---------------------------------------------------------------------------


class TestValidatePlanActions:
    """``validate_plan_actions`` produce un reporte de verificación estructurado."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_all_existing_actions(self):
        """Un plan con solo acciones registradas → valid: True, sin inexistentes."""
        plan = [
            {"id": "step1", "action": "open_application"},
            {"id": "step2", "action": "type_text"},
            {"id": "step3", "action": "navigate_enter"},
        ]
        result = self.planner.validate_plan_actions(plan)
        assert result["total_steps"] == 3
        assert result["valid"] is True
        assert result["nonexistent_actions"] == []
        assert result["steps_with_callback"] == 0
        assert set(result["existing_actions"]) == {"open_application", "type_text", "navigate_enter"}
        assert result["valid_steps"] == 3

    def test_mixed_existing_and_nonexistent(self):
        """Un plan con acciones existentes y no existentes → valid: False."""
        plan = [
            {"id": "step1", "action": "open_application"},
            {"id": "press_enter", "action": "press_enter"},
            {"id": "step3", "action": "type_text"},
        ]
        result = self.planner.validate_plan_actions(plan)
        assert result["total_steps"] == 3
        assert result["valid"] is False
        assert result["nonexistent_actions"] == ["press_enter"]
        assert result["existing_actions"] == ["open_application", "type_text"]
        assert result["steps_with_callback"] == 0
        assert result["valid_steps"] == 2

    def test_node_with_callback_is_valid(self):
        """Pasos con ``execute_callback`` cuentan como válidos sin verificación."""
        callback = MagicMock()
        plan = [
            {"id": "custom", "execute_callback": callback},
            {"id": "press_enter", "action": "press_enter"},
        ]
        result = self.planner.validate_plan_actions(plan)
        assert result["total_steps"] == 2
        assert result["steps_with_callback"] == 1
        assert result["nonexistent_actions"] == ["press_enter"]
        assert result["valid"] is False
        assert result["valid_steps"] == 1

    def test_all_callbacks_valid(self):
        """Un plan donde todos los pasos tienen callback → valid: True."""
        cb = MagicMock()
        plan = [
            {"id": "s1", "action": "whatever", "execute_callback": cb},
            {"id": "s2", "action": "whatever2", "metadata": {"execute_callback": cb}},
        ]
        result = self.planner.validate_plan_actions(plan)
        assert result["valid"] is True
        assert result["nonexistent_actions"] == []
        assert result["steps_with_callback"] == 2

    def test_empty_plan(self):
        result = self.planner.validate_plan_actions([])
        assert result["total_steps"] == 0
        assert result["valid"] is True
        assert result["nonexistent_actions"] == []

    def test_none_plan_treated_as_empty(self):
        result = self.planner.validate_plan_actions(None)
        assert result["total_steps"] == 0

    def test_non_dict_steps_skipped(self):
        plan = ["string_step", 42, {"id": "valid", "action": "open_application"}]
        result = self.planner.validate_plan_actions(plan)
        assert result["total_steps"] == 3
        assert result["existing_actions"] == ["open_application"]
        assert result["nonexistent_actions"] == []

    def test_resolution_via_metadata_action_name(self):
        """``metadata['action_name']`` resuelve a una acción registrada."""
        plan = [
            {
                "id": "step_1",
                "action": "step_1",
                "metadata": {"action_name": "open_application"},
            }
        ]
        result = self.planner.validate_plan_actions(plan)
        assert result["valid"] is True
        assert result["existing_actions"] == ["open_application"]

    def test_resolution_via_metadata_action(self):
        """``metadata['action']`` resuelve a una acción registrada."""
        plan = [
            {
                "id": "step_1",
                "action": "step_1",
                "metadata": {"action": "type_text"},
            }
        ]
        result = self.planner.validate_plan_actions(plan)
        assert result["valid"] is True
        assert result["existing_actions"] == ["type_text"]


# ---------------------------------------------------------------------------
# filter_existing_actions
# ---------------------------------------------------------------------------


class TestFilterExistingActions:
    """``filter_existing_actions`` devuelve un plan con solo pasos ejecutables."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_filters_nonexistent_keeps_existing(self):
        plan = [
            {"id": "step1", "action": "open_application"},
            {"id": "press_enter", "action": "press_enter"},
            {"id": "step3", "action": "type_text"},
        ]
        filtered = self.planner.filter_existing_actions(plan)
        actions = [s["action"] for s in filtered]
        assert "press_enter" not in actions
        assert "open_application" in actions
        assert "type_text" in actions
        assert len(filtered) == 2

    def test_keeps_callback_steps(self):
        cb = MagicMock()
        plan = [
            {"id": "custom", "execute_callback": cb},
            {"id": "press_enter", "action": "press_enter"},
        ]
        filtered = self.planner.filter_existing_actions(plan)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "custom"

    def test_all_filtered_returns_empty(self):
        plan = [
            {"id": "press_enter", "action": "press_enter"},
            {"id": "chrome_open", "action": "chrome_open"},
        ]
        filtered = self.planner.filter_existing_actions(plan)
        assert filtered == []

    def test_empty_plan_returns_empty(self):
        assert self.planner.filter_existing_actions([]) == []

    def test_original_plan_not_mutated(self):
        plan = [
            {"id": "step1", "action": "open_application"},
            {"id": "press_enter", "action": "press_enter"},
        ]
        original_len = len(plan)
        _ = self.planner.filter_existing_actions(plan)
        assert len(plan) == original_len

    def test_no_registry_preserves_all(self):
        """Sin ActionRegistry disponible, el plan se conserva sin filtrar."""
        planner = Planner()
        planner.executor = None
        with patch.object(planner, "_get_action_registry", return_value=None):
            plan = [
                {"id": "press_enter", "action": "press_enter"},
                {"id": "chrome_open", "action": "chrome_open"},
            ]
            filtered = planner.filter_existing_actions(plan)
            assert len(filtered) == 2


# ---------------------------------------------------------------------------
# Integración en _create_plan
# ---------------------------------------------------------------------------


class TestCreatePlanVerification:
    """``_create_plan`` incluye ``action_verification`` en la metadata del
    resultado y reporta advertencias sobre acciones inexistentes."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_plan_result_has_action_verification_metadata(self):
        """El PlanningResult de ``_create_plan`` incluye la clave
        ``action_verification`` en metadata."""
        goal = Goal(
            id="g-verif",
            type="open_application",
            target={"app_name": "chrome"},
            description="Abrir Chrome",
        )
        result = self.planner._create_plan(
            goal, self.planner._normalize_state({}), self.planner._get_available_nodes(), 30.0
        )
        assert "action_verification" in result.metadata
        verification = result.metadata["action_verification"]
        assert isinstance(verification, dict)
        assert "total_steps" in verification
        assert "nonexistent_actions" in verification
        assert "valid" in verification

    def test_plan_result_warns_on_nonexistent_actions(self):
        """Cuando el plan contiene acciones inexistentes, aparecen como warnings."""
        goal = Goal(
            id="g-verif-2",
            type="open_application",
            target={"app_name": "chrome"},
            description="Abrir Chrome",
        )
        result = self.planner._create_plan(
            goal, self.planner._normalize_state({}), self.planner._get_available_nodes(), 30.0
        )
        verification = result.metadata["action_verification"]
        if verification["nonexistent_actions"]:
            # Al menos una advertencia menciona las acciones inexistentes
            found = any(
                "inexistentes" in w.lower()
                for w in result.warnings
            )
            assert found, f"Expected warning about nonexistent actions, got: {result.warnings}"

    def test_plan_result_valid_when_no_actions(self):
        """Un plan vacío (goal already achieved) → verification con 0 steps, valid True."""
        goal = Goal(
            id="g-achieved",
            type="open_application",
            target={"app_name": "chrome"},
            description="Abrir Chrome",
        )
        state = self.planner._normalize_state({"chrome_open": True, "chrome_active": True})
        result = self.planner._create_plan(
            goal, state, self.planner._get_available_nodes(), 30.0
        )
        verification = result.metadata["action_verification"]
        assert verification["total_steps"] == 0
        assert verification["valid"] is True


# ---------------------------------------------------------------------------
# Integración en build_application_aware_plan
# ---------------------------------------------------------------------------


class TestBuildApplicationAwarePlanVerification:
    """``build_application_aware_plan`` expone ``action_verification`` en metadata."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_plan_metadata_includes_action_verification(self):
        """La planificación conscious-de-aplicación incluye la verificación de
        acciones en la metadata del resultado."""
        goal = Goal(
            id="g-app-verif",
            type="open_application",
            target={"app_name": "chrome"},
            description="Abrir Chrome",
        )
        result = self.planner.build_application_aware_plan(goal, {})
        assert "action_verification" in result.metadata
        verification = result.metadata["action_verification"]
        assert isinstance(verification, dict)
        assert "total_steps" in verification
        assert "nonexistent_actions" in verification
        assert "valid" in verification


# ---------------------------------------------------------------------------
# ActionRegistry no disponible
# ---------------------------------------------------------------------------


class TestNoActionRegistry:
    """Cuando el ActionRegistry no está disponible, la verificación es segura."""

    @pytest.fixture(autouse=True)
    def _setup_planner(self):
        self.planner = _planner()

    def test_action_exists_returns_false_without_registry(self):
        """Sin ActionRegistry → ``action_exists`` devuelve False (modo paso seguro)."""
        with patch.object(self.planner, "_get_action_registry", return_value=None):
            assert self.planner.action_exists("any_action") is False

    def test_validate_plan_without_registry_keeps_all_valid(self):
        """Sin ActionRegistry, todos los pasos se conservan como válidos (no callbacks
        necesarios).  Ninguna acción se marca como inexistente."""
        with patch.object(self.planner, "_get_action_registry", return_value=None):
            plan = [
                {"id": "press_enter", "action": "press_enter"},
                {"id": "chrome_open", "action": "chrome_open"},
            ]
            result = self.planner.validate_plan_actions(plan)
            assert result["nonexistent_actions"] == []
            assert result["valid"] is True
            assert result["valid_steps"] == 2

    def test_filter_without_registry_preserves_all(self):
        """Sin ActionRegistry, ``filter_existing_actions`` conserva todo el plan."""
        with patch.object(self.planner, "_get_action_registry", return_value=None):
            plan = [
                {"id": "press_enter", "action": "press_enter"},
                {"id": "chrome_open", "action": "chrome_open"},
            ]
            filtered = self.planner.filter_existing_actions(plan)
            assert len(filtered) == 2
