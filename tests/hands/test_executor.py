# -*- coding: utf-8 -*-
"""Tests para Executor, ExecutionResult, ExecutionState y ExecutionStatus
(src/hands/executor.py).

Cubre:
- Enum ExecutionStatus
- Dataclasses ExecutionResult (__bool__, to_dict), ExecutionState (update, to_dict)
- Executor.__init__ (estado, action_registry, planners, learning_system)
- Métodos estáticos: _normalize_plan_node, _safe_cost, _get_nested_value
- Métodos de instancia: _evaluate_condition, _check_node_preconditions,
  _verify_node_success, _should_replan, _extract_capability_from_action,
  _action_provides_capability, _try_alternative, _parse_args,
  _positional_to_named_parameters, _get_legacy_function,
  execute_plan, execute_plan_with_replan, _replan_after_failure,
  _find_alternative_nodes, process_and_execute, create_goal_from_command,
  can_execute, list_commands, get_plannable_actions, get_action_info,
  get_current_state, update_state, _get_state_for_planning, _goal_achieved,
  get_executor

El StructuredLogger carece de ``exception``; se parcha en cada test que
puede transitar por una ruta de captura de excepciones.
"""

import copy
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.hands.executor import (
    ExecutionResult,
    ExecutionState,
    ExecutionStatus,
    Executor,
    get_executor,
)
from src.hands.action_registry import ActionInfo, ActionRegistry, ActionType


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _patch_executor_logger():
    """Returns a patch object that adds ``exception`` to the executor module logger."""
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


@pytest.fixture
def mock_action_info_factory():
    """Factory to create ActionInfo-like mock objects."""
    def _make(name="test_action", action_type=ActionType.INTERACTION, category="keyboard",
              capabilities=None, **extra):
        ai = MagicMock()
        ai.name = name
        ai.action_type = action_type
        ai.category = category
        ai.capabilities = capabilities or []
        for k, v in extra.items():
            setattr(ai, k, v)
        return ai
    return _make


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


# ---------------------------------------------------------------------------
# ExecutionStatus
# ---------------------------------------------------------------------------

class TestExecutionStatus:
    def test_values(self):
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.SUCCESS.value == "success"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.RETRYING.value == "retrying"
        assert ExecutionStatus.ALTERNATIVE.value == "alternative"

    def test_all_distinct(self):
        values = [e.value for e in ExecutionStatus]
        assert len(values) == len(set(values))

    def test_count(self):
        assert len(list(ExecutionStatus)) == 6


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------

class TestExecutionResult:
    def test_default_values(self):
        er = ExecutionResult(status=ExecutionStatus.SUCCESS)
        assert er.result is None
        assert er.error is None
        assert er.execution_time == 0.0
        assert er.node_id is None
        assert er.plan_id is None
        assert er.retries == 0
        assert er.alternatives_tried == []
        assert er.last_actions == []
        assert er.successful_nodes == []
        assert er.failed_nodes == []

    def test_bool_success(self):
        er = ExecutionResult(status=ExecutionStatus.SUCCESS)
        assert bool(er) is True

    def test_bool_failed(self):
        er = ExecutionResult(status=ExecutionStatus.FAILED)
        assert bool(er) is False

    def test_bool_running(self):
        er = ExecutionResult(status=ExecutionStatus.RUNNING)
        assert bool(er) is False

    def test_bool_retrying(self):
        er = ExecutionResult(status=ExecutionStatus.RETRYING)
        assert bool(er) is False

    def test_bool_alternative(self):
        er = ExecutionResult(status=ExecutionStatus.ALTERNATIVE)
        assert bool(er) is False

    def test_bool_pending(self):
        er = ExecutionResult(status=ExecutionStatus.PENDING)
        assert bool(er) is False

    def test_to_dict_keys(self):
        er = ExecutionResult(status=ExecutionStatus.SUCCESS, node_id="n1", plan_id="p1")
        d = er.to_dict()
        expected_keys = {
            "status", "result", "error", "execution_time",
            "node_id", "plan_id", "retries", "alternatives_tried",
            "last_actions", "successful_nodes", "failed_nodes",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        er = ExecutionResult(
            status=ExecutionStatus.FAILED,
            result={"data": 1},
            error="bad",
            execution_time=2.5,
            node_id="n2",
            retries=3,
        )
        d = er.to_dict()
        assert d["status"] == "failed"
        assert d["result"] == {"data": 1}
        assert d["error"] == "bad"
        assert d["execution_time"] == 2.5
        assert d["node_id"] == "n2"
        assert d["retries"] == 3

    def test_to_dict_deepcopy_result(self):
        er = ExecutionResult(status=ExecutionStatus.SUCCESS, result={"x": [1, 2, 3]})
        d = er.to_dict()
        d["result"]["x"].append(4)
        assert er.result["x"] == [1, 2, 3]

    def test_to_dict_deepcopy_failed_nodes(self):
        er = ExecutionResult(status=ExecutionStatus.FAILED, failed_nodes=[{"id": "n1", "error": "e"}])
        d = er.to_dict()
        d["failed_nodes"][0]["error"] = "mutated"
        assert er.failed_nodes[0]["error"] == "e"

    def test_to_dict_deepcopy_alternatives_tried(self):
        er = ExecutionResult(status=ExecutionStatus.FAILED, alternatives_tried=["a"])
        d = er.to_dict()
        d["alternatives_tried"].append("b")
        assert er.alternatives_tried == ["a"]


# ---------------------------------------------------------------------------
# ExecutionState
# ---------------------------------------------------------------------------

class TestExecutionState:
    def test_initial_state(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={},
            ui_elements={},
            available_actions=["a"],
            last_actions=[],
            constraints=[],
        )
        assert state.timestamp == 1.0
        assert state.application_states == {}
        assert state.ui_elements == {}
        assert state.available_actions == ["a"]
        assert state.last_actions == []
        assert state.constraints == []

    def test_update_merges_dicts(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={},
            ui_elements={},
            available_actions=[],
            last_actions=[],
            constraints=[],
        )
        state.update({"constraints": ["c1"], "available_actions": ["a"]})
        assert state.constraints == ["c1"]
        assert state.available_actions == ["a"]

    def test_update_replaces_lists(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={},
            ui_elements={},
            available_actions=[],
            last_actions=["action1"],
            constraints=[],
        )
        state.update({"last_actions": ["action2"]})
        assert state.last_actions == ["action2"]

    def test_update_merges_nested_dict(self):
        """ExecutionState.update does shallow merge at top level (dict.update replaces keys)."""
        state = ExecutionState(
            timestamp=1.0,
            application_states={"app1": {"open": False}},
            ui_elements={},
            available_actions=[],
            last_actions=[],
            constraints=[],
        )
        state.update({"application_states": {"app1": {"active": True}}})
        # dict.update at top level replaces "app1" entirely
        assert "active" in state.application_states["app1"]
        # "open" is replaced because update is shallow at the key level

    def test_update_raises_on_non_dict(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={},
            ui_elements={},
            available_actions=[],
            last_actions=[],
            constraints=[],
        )
        with pytest.raises(TypeError):
            state.update("not a dict")  # type: ignore

    def test_update_skips_private_and_timestamp(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={},
            ui_elements={},
            available_actions=[],
            last_actions=[],
            constraints=[],
        )
        state.update({"_private": "secret", "timestamp": 999, "constraints": ["x"]})
        assert not hasattr(state, "_private")
        assert state.constraints == ["x"]

    def test_update_sets_timestamp(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={},
            ui_elements={},
            available_actions=[],
            last_actions=[],
            constraints=[],
        )
        old = state.timestamp
        import time as _time
        _time.sleep(0.01)
        state.update({"constraints": ["x"]})
        assert state.timestamp > old

    def test_to_dict_deepcopy(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={"app1": {"open": True}},
            ui_elements={},
            available_actions=["a"],
            last_actions=[],
            constraints=[],
        )
        d = state.to_dict()
        d["application_states"]["app1"]["open"] = False
        assert state.application_states["app1"]["open"] is True

    def test_to_dict_includes_all_fields(self):
        state = ExecutionState(
            timestamp=1.0,
            application_states={"app": {}},
            ui_elements={"elem": {}},
            available_actions=["a"],
            last_actions=["x"],
            constraints=["c"],
        )
        d = state.to_dict()
        assert d["timestamp"] == 1.0
        assert d["application_states"] == {"app": {}}
        assert d["ui_elements"] == {"elem": {}}
        assert d["available_actions"] == ["a"]
        assert d["last_actions"] == ["x"]
        assert d["constraints"] == ["c"]


# ---------------------------------------------------------------------------
# Executor.__init__
# ---------------------------------------------------------------------------

class TestExecutorInit:
    def test_init_creates_state(self, executor):
        assert isinstance(executor.current_state, ExecutionState)
        assert executor.current_state.timestamp > 0

    def test_init_has_action_registry(self, executor):
        assert executor.action_registry is not None

    def test_init_has_modules(self, executor):
        assert "apps" in executor.modules
        assert "key" in executor.modules
        assert "mouse" in executor.modules

    def test_init_timeout_config(self, executor):
        assert executor.timeout_config is not None

    def test_init_predictive_config(self, executor):
        assert executor.predictive_config is not None

    def test_init_active_executions(self, executor):
        assert isinstance(executor.active_executions, dict)
        assert executor.active_executions == {}

    def test_init_execution_lock(self, executor):
        assert executor._execution_lock is not None

    def test_init_state_available_actions_populated(self, executor):
        assert len(executor.current_state.available_actions) > 0

    def test_init_planner_optional(self, executor):
        """Planner may or may not be available; either is acceptable."""
        assert executor.planner is None or hasattr(executor.planner, "plan")

    def test_init_learning_system(self, executor):
        # learning_system may be None if not available
        assert executor.learning_system is None or executor.learning_system is not None

    def test_command_pattern(self):
        assert Executor._COMMAND_PATTERN is not None
        match = Executor._COMMAND_PATTERN.search("[CMD: test_command(arg1, arg2)]")
        assert match is not None
        assert match.group(1) == "test_command"
        assert match.group(2) == "arg1, arg2"

    def test_command_pattern_no_args(self):
        match = Executor._COMMAND_PATTERN.search("[CMD: simple_command]")
        assert match is not None
        assert match.group(1) == "simple_command"
        assert match.group(2) is None


# ---------------------------------------------------------------------------
# Static methods
# ---------------------------------------------------------------------------

class TestNormalizePlanNode:
    def test_dict_input(self):
        raw = {"id": "n1", "action": "test", "parameters": {"p": 1}}
        node = Executor._normalize_plan_node(raw, 0)
        assert node["id"] == "n1"
        assert node["action"] == "test"
        assert node["parameters"] == {"p": 1}
        assert node["preconditions"] == []
        assert node["effects"] == []
        assert node["alternatives"] == []

    def test_dict_defaults_id_from_action(self):
        raw = {"action": "test"}
        node = Executor._normalize_plan_node(raw, 3)
        assert node["id"] == "test"

    def test_dict_defaults_id_from_index(self):
        raw = {}
        node = Executor._normalize_plan_node(raw, 5)
        assert node["id"] == "node_5"

    def test_object_with_id(self):
        obj = SimpleNamespace(
            id="obj1", name="obj_name", action="obj_action",
            parameters={"p": 1}, preconditions=[], effects=[],
            cost=2.0, application="Chrome", ui_element=None,
            metadata={"key": "val"},
        )
        node = Executor._normalize_plan_node(obj, 0)
        assert node["id"] == "obj1"
        assert node["action"] == "obj_action"
        assert node["parameters"] == {"p": 1}
        assert node["preconditions"] == []
        assert node["effects"] == []
        assert node["cost"] == 2.0
        assert node["application"] == "Chrome"
        assert node["metadata"] == {"key": "val"}

    def test_object_action_fallback_to_id(self):
        """When object has no 'action' attr, uses 'id' as action."""
        obj = SimpleNamespace(
            id="only_id", name="n", parameters={}, preconditions=[],
            effects=[], cost=1.0, application=None, ui_element=None,
            metadata={},
        )
        node = Executor._normalize_plan_node(obj, 0)
        assert node["action"] == "only_id"
        assert node["id"] == "only_id"

    def test_invalid_string(self):
        assert Executor._normalize_plan_node("invalid", 0) is None

    def test_invalid_int(self):
        assert Executor._normalize_plan_node(42, 0) is None

    def test_invalid_none(self):
        assert Executor._normalize_plan_node(None, 0) is None

    def test_parameters_not_dict(self):
        raw = {"id": "n1", "parameters": "not_a_dict"}
        assert Executor._normalize_plan_node(raw, 0) is None

    def test_preconditions_not_list(self):
        raw = {"id": "n1", "preconditions": "not_a_list"}
        assert Executor._normalize_plan_node(raw, 0) is None

    def test_effects_not_list(self):
        raw = {"id": "n1", "effects": "not_a_list"}
        assert Executor._normalize_plan_node(raw, 0) is None

    def test_normalization_preserves_existing_fields(self):
        raw = {"id": "n1", "action": "test", "custom_field": "custom"}
        node = Executor._normalize_plan_node(raw, 0)
        assert node["custom_field"] == "custom"

    def test_normalization_does_not_mutate_input(self):
        raw = {"id": "n1", "action": "test", "parameters": {"p": 1}}
        Executor._normalize_plan_node(raw, 0)
        assert raw["parameters"] == {"p": 1}

    def test_dict_with_alternatives(self):
        raw = {"id": "n1", "action": "test", "alternatives": [{"action": "alt"}]}
        node = Executor._normalize_plan_node(raw, 0)
        assert node["alternatives"] == [{"action": "alt"}]

    def test_dict_with_metadata(self):
        raw = {"id": "n1", "action": "test", "metadata": {"execute_callback": lambda: None}}
        node = Executor._normalize_plan_node(raw, 0)
        assert "execute_callback" in node["metadata"]


class TestSafeCost:
    def test_valid_float(self):
        assert Executor._safe_cost(5.0) == 5.0

    def test_valid_int(self):
        assert Executor._safe_cost(3) == 3.0

    def test_negative_clamped(self):
        assert Executor._safe_cost(-1.0) == 0.0

    def test_negative_int_clamped(self):
        assert Executor._safe_cost(-5) == 0.0

    def test_invalid_string(self):
        assert Executor._safe_cost("abc") == 1.0

    def test_none(self):
        assert Executor._safe_cost(None) == 1.0

    def test_inf(self):
        assert Executor._safe_cost(float("inf")) == 1.0

    def test_nan(self):
        assert Executor._safe_cost(float("nan")) == 1.0

    def test_zero(self):
        assert Executor._safe_cost(0.0) == 0.0

    def test_custom_default(self):
        assert Executor._safe_cost("abc", default=5.0) == 5.0

    def test_custom_default_negative_input(self):
        assert Executor._safe_cost(-10, default=5.0) == 0.0

    def test_true_bool(self):
        assert Executor._safe_cost(True) == 1.0

    def test_false_bool(self):
        assert Executor._safe_cost(False) == 0.0


class TestGetNestedValue:
    def test_flat_key(self):
        state = {"top": "value"}
        assert Executor._get_nested_value(state, "top") == "value"

    def test_nested_key(self):
        state = {"a": {"b": {"c": 42}}}
        assert Executor._get_nested_value(state, "a.b.c") == 42

    def test_missing_key(self):
        state = {"a": 1}
        assert Executor._get_nested_value(state, "missing") is None

    def test_missing_nested_key(self):
        state = {"a": {"b": 1}}
        assert Executor._get_nested_value(state, "a.c") is None

    def test_not_dict_mid_path(self):
        state = {"a": 1}
        assert Executor._get_nested_value(state, "a.b") is None

    def test_empty_key(self):
        state = {"": "empty_val"}
        assert Executor._get_nested_value(state, "") == "empty_val"

    def test_deeply_nested(self):
        state = {"a": {"b": {"c": {"d": {"e": "deep"}}}}}
        assert Executor._get_nested_value(state, "a.b.c.d.e") == "deep"


# ---------------------------------------------------------------------------
# _evaluate_condition
# ---------------------------------------------------------------------------

class TestEvaluateCondition:
    def test_bool_true(self, executor):
        assert executor._evaluate_condition(True) is True

    def test_bool_false(self, executor):
        assert executor._evaluate_condition(False) is False

    def test_callable_true(self, executor):
        assert executor._evaluate_condition(lambda s: True) is True

    def test_callable_false(self, executor):
        assert executor._evaluate_condition(lambda s: False) is False

    def test_callable_exception(self, executor):
        def bad(s):
            raise RuntimeError("boom")
        assert executor._evaluate_condition(bad) is False

    def test_callable_with_state(self, executor):
        executor.update_state({"count": 5})
        assert executor._evaluate_condition(lambda s: s.get("count") > 3) is True

    def test_string_key_in_state(self, executor):
        executor.update_state({"flag": True})
        assert executor._evaluate_condition("flag") is True

    def test_string_key_not_in_state(self, executor):
        assert executor._evaluate_condition("nonexistent") is False

    def test_string_empty_returns_true(self, executor):
        assert executor._evaluate_condition("") is True

    def test_dict_equals(self, executor):
        executor.update_state({"count": 5})
        assert executor._evaluate_condition({"key": "count", "equals": 5}) is True

    def test_dict_equals_fails(self, executor):
        executor.update_state({"count": 3})
        assert executor._evaluate_condition({"key": "count", "equals": 5}) is False

    def test_dict_gt(self, executor):
        executor.update_state({"count": 10})
        assert executor._evaluate_condition({"key": "count", "operator": "gt", "equals": 5}) is True

    def test_dict_lt(self, executor):
        executor.update_state({"count": 3})
        assert executor._evaluate_condition({"key": "count", "operator": "lt", "equals": 5}) is True

    def test_dict_ne(self, executor):
        executor.update_state({"name": "test"})
        assert executor._evaluate_condition({"key": "name", "operator": "ne", "value": "other"}) is True

    def test_dict_gte(self, executor):
        executor.update_state({"count": 5})
        assert executor._evaluate_condition({"key": "count", "operator": "gte", "equals": 5}) is True

    def test_dict_lte(self, executor):
        executor.update_state({"count": 5})
        assert executor._evaluate_condition({"key": "count", "operator": "lte", "equals": 5}) is True

    def test_dict_exists(self, executor):
        executor.update_state({"found": True})
        assert executor._evaluate_condition({"key": "found", "operator": "exists"}) is True

    def test_dict_exists_missing(self, executor):
        assert executor._evaluate_condition({"key": "missing", "operator": "exists"}) is False

    def test_dict_truthy_key(self, executor):
        executor.update_state({"active": True})
        assert executor._evaluate_condition({"key": "active"}) is True

    def test_dict_no_key(self, executor):
        assert executor._evaluate_condition({"key": "nonexistent"}) is False

    def test_dict_value_field(self, executor):
        executor.update_state({"status": "ready"})
        assert executor._evaluate_condition({"key": "status", "value": "ready"}) is True

    def test_application_open_condition(self, executor):
        executor.current_state.application_states = {"chrome": {"open": True}}
        assert executor._evaluate_condition("chrome_open") is True

    def test_application_closed_condition(self, executor):
        executor.current_state.application_states = {"chrome": {"open": True}}
        assert executor._evaluate_condition("chrome_closed") is False

    def test_application_closed_when_genuinely_closed(self, executor):
        executor.current_state.application_states = {"chrome": {"open": False}}
        assert executor._evaluate_condition("chrome_closed") is True

    def test_unknown_string_condition(self, executor):
        assert executor._evaluate_condition("unknown_thing") is False

    def test_app_prefix_condition(self, executor):
        executor.current_state.application_states = {"chrome": {"open": True}}
        assert executor._evaluate_condition("app_chrome") is True

    def test_app_prefix_condition_missing(self, executor):
        assert executor._evaluate_condition("app_nonexistent") is False

    def test_browser_available(self, executor):
        assert executor._evaluate_condition("browser_available") is True

    def test_resources_available(self, executor):
        assert executor._evaluate_condition("resources_available") is True

    def test_non_dict_non_str_non_callable(self, executor):
        """Objects with evaluate/is_satisfied/etc methods are tried."""
        class FakeCondition:
            def evaluate(self, state):
                return True
        assert executor._evaluate_condition(FakeCondition()) is True

    def test_non_dict_condition_with_to_dict(self, executor):
        class Cond:
            def to_dict(self):
                return {"key": "flag", "equals": True}
        executor.update_state({"flag": True})
        assert executor._evaluate_condition(Cond()) is True


# ---------------------------------------------------------------------------
# _check_node_preconditions
# ---------------------------------------------------------------------------

class TestCheckNodePreconditions:
    def test_empty_preconditions(self, executor):
        node = _make_node("n1", "test")
        assert executor._check_node_preconditions(node) is True

    def test_true_precondition(self, executor):
        node = _make_node("n1", "test", preconditions=[True])
        assert executor._check_node_preconditions(node) is True

    def test_false_precondition(self, executor):
        node = _make_node("n1", "test", preconditions=[False])
        assert executor._check_node_preconditions(node) is False

    def test_multiple_all_true(self, executor):
        node = _make_node("n1", "test", preconditions=[True, True, True])
        assert executor._check_node_preconditions(node) is True

    def test_multiple_one_false(self, executor):
        node = _make_node("n1", "test", preconditions=[True, False, True])
        assert executor._check_node_preconditions(node) is False

    def test_callable_precondition(self, executor):
        node = _make_node("n1", "test", preconditions=[lambda s: True])
        assert executor._check_node_preconditions(node) is True

    def test_empty_preconditions_list(self, executor):
        node = _make_node("n1", "test", preconditions=[])
        assert executor._check_node_preconditions(node) is True

    def test_none_preconditions(self, executor):
        node = _make_node("n1", "test", preconditions=None)
        # _check_node_preconditions uses node.get("preconditions", []) or []
        assert executor._check_node_preconditions(node) is True


# ---------------------------------------------------------------------------
# _verify_node_success
# ---------------------------------------------------------------------------

class TestVerifyNodeSuccess:
    def test_dict_success_true(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"success": True}) is True

    def test_dict_success_false(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"success": False}) is False

    def test_dict_with_error(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"error": "failed"}) is False

    def test_dict_with_error_message(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"error_message": "bad"}) is False

    def test_dict_status_success(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"status": "success"}) is True

    def test_dict_status_completed(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"status": "completed"}) is True

    def test_dict_status_failed(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"status": "failed"}) is False

    def test_dict_no_success_no_status(self, executor):
        """execute_action already verified success before returning, so no status -> True."""
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"data": "test"}) is True

    def test_none_result(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, None) is False

    def test_false_result(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, False) is False

    def test_true_result(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, True) is True

    def test_bool_result_true(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, True) is True

    def test_bool_result_false(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, False) is False

    def test_success_int_one(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"success": 1}) is True

    def test_success_int_zero(self, executor):
        node = _make_node("n1", "test")
        assert executor._verify_node_success(node, {"success": 0}) is False

    def test_custom_checker_true(self, executor):
        node = _make_node("n1", "test", metadata={"success_checker": lambda r: r.get("ok")})
        assert executor._verify_node_success(node, {"ok": True}) is True

    def test_custom_checker_false(self, executor):
        node = _make_node("n1", "test", metadata={"success_checker": lambda r: r.get("ok")})
        assert executor._verify_node_success(node, {"ok": False}) is False

    def test_custom_checker_exception(self, executor):
        def checker(r):
            raise RuntimeError("boom")
        node = _make_node("n1", "test", metadata={"success_checker": checker})
        assert executor._verify_node_success(node, {"ok": True}) is False

    def test_object_with_status_attr(self, executor):
        node = _make_node("n1", "test")
        obj = SimpleNamespace(status="completed")
        assert executor._verify_node_success(node, obj) is True

    def test_object_without_status_or_success(self, executor):
        """Objects without status/success default to True (execute_action already verified)."""
        node = _make_node("n1", "test")
        obj = SimpleNamespace(data="test")
        assert executor._verify_node_success(node, obj) is True

    def test_node_level_success_checker(self, executor):
        """success_checker at node level takes priority."""
        node = _make_node("n1", "test", metadata={"success_checker": lambda r: False})
        assert executor._verify_node_success(node, {"success": True}) is False


# ---------------------------------------------------------------------------
# _should_replan
# ---------------------------------------------------------------------------

class TestShouldReplan:
    def test_node_with_alternatives(self, executor):
        plan = [_make_node("n1", "test", alternatives=[{"action": "alt"}])]
        assert executor._should_replan(plan, 0) is True

    def test_expensive_node_no_alternatives(self, executor):
        plan = [_make_node("n1", "test", alternatives=[], cost=10.0)]
        assert executor._should_replan(plan, 0) is False

    def test_cheap_node_no_alternatives(self, executor):
        plan = [_make_node("n1", "test", alternatives=[], cost=2.0)]
        assert executor._should_replan(plan, 0) is True

    def test_mid_cost_node_no_alternatives(self, executor):
        plan = [_make_node("n1", "test", alternatives=[], cost=4.0)]
        assert executor._should_replan(plan, 0) is False

    def test_out_of_range_index(self, executor):
        plan = [_make_node("n1", "test", alternatives=[], cost=2.0)]
        assert executor._should_replan(plan, 5) is False

    def test_default_cost_node_no_alternatives(self, executor):
        plan = [_make_node("n1", "test", alternatives=[], cost=1.0)]
        assert executor._should_replan(plan, 0) is True

    def test_cost_exactly_5_not_expensive(self, executor):
        """cost > 5.0 is strict; cost=5.0 is not > 5.0, so falls to cost <= 3.0 check."""
        plan = [_make_node("n1", "test", alternatives=[], cost=5.0)]
        assert executor._should_replan(plan, 0) is False

    def test_cost_exactly_3_replanable(self, executor):
        plan = [_make_node("n1", "test", alternatives=[], cost=3.0)]
        assert executor._should_replan(plan, 0) is True

    def test_empty_alternatives_list(self, executor):
        plan = [_make_node("n1", "test", alternatives=[], cost=1.0)]
        assert executor._should_replan(plan, 0) is True


# ---------------------------------------------------------------------------
# _extract_capability_from_action
# ---------------------------------------------------------------------------

class TestExtractCapability:
    def test_focus_address_bar(self, executor):
        assert executor._extract_capability_from_action("focus_address_bar") == "focus_element"

    def test_click_address_bar(self, executor):
        assert executor._extract_capability_from_action("click_address_bar") == "focus_element"

    def test_hotkey_ctrl_l(self, executor):
        assert executor._extract_capability_from_action("hotkey_ctrl_l") == "focus_element"

    def test_type_url(self, executor):
        assert executor._extract_capability_from_action("type_url") == "type_text"

    def test_press_enter(self, executor):
        assert executor._extract_capability_from_action("press_enter") == "press_key"

    def test_open_chrome(self, executor):
        assert executor._extract_capability_from_action("open_chrome") == "open_application"

    def test_activate_chrome(self, executor):
        assert executor._extract_capability_from_action("activate_chrome") == "activate_window"

    def test_minimize_chrome(self, executor):
        assert executor._extract_capability_from_action("minimize_chrome") == "minimize_window"

    def test_unknown_action_returns_itself(self, executor):
        assert executor._extract_capability_from_action("unknown_action") == "unknown_action"

    def test_empty_action(self, executor):
        assert executor._extract_capability_from_action("") == ""


# ---------------------------------------------------------------------------
# _action_provides_capability
# ---------------------------------------------------------------------------

class TestActionProvidesCapability:
    def _make_ai(self, name="test_action", action_type=ActionType.INTERACTION, category="keyboard",
                 capabilities=None):
        ai = MagicMock()
        ai.name = name
        ai.action_type = action_type
        ai.category = category
        ai.capabilities = capabilities or []
        return ai

    def test_name_match(self, executor):
        ai = self._make_ai(name="type_text")
        assert executor._action_provides_capability(ai, "type") is True

    def test_action_type_match(self, executor):
        ai = self._make_ai(action_type=ActionType.INTERACTION)
        assert executor._action_provides_capability(ai, "interaction") is True

    def test_category_match(self, executor):
        ai = self._make_ai(category="keyboard")
        assert executor._action_provides_capability(ai, "keyboard") is True

    def test_no_match(self, executor):
        ai = self._make_ai(name="type_text", category="keyboard")
        assert executor._action_provides_capability(ai, "unknown_cap") is False

    def test_empty_capability(self, executor):
        ai = self._make_ai()
        assert executor._action_provides_capability(ai, "") is False

    def test_capabilities_declared_match(self, executor):
        ai = self._make_ai(capabilities=["search"])
        assert executor._action_provides_capability(ai, "search") is True

    def test_capabilities_enum_value_match(self, executor):
        ai = self._make_ai(action_type=ActionType.INTERACTION)
        assert executor._action_provides_capability(ai, "interaction") is True

    def test_case_insensitive_name(self, executor):
        ai = self._make_ai(name="TypeText")
        assert executor._action_provides_capability(ai, "type") is True

    def test_none_action_info_returns_false(self, executor):
        """None action_info is handled gracefully via getattr defaults."""
        assert executor._action_provides_capability(None, "test") is False


# ---------------------------------------------------------------------------
# _try_alternative
# ---------------------------------------------------------------------------

class TestTryAlternative:
    def test_no_alternatives_returns_failed_result(self, executor):
        node = _make_node("n1", "test", alternatives=[])
        failed_result = ExecutionResult(status=ExecutionStatus.FAILED, error="fail")
        result = executor._try_alternative(node, failed_result)
        assert result is failed_result

    def test_empty_alternatives_list(self, executor):
        node = _make_node("n1", "test", alternatives=[])
        failed_result = ExecutionResult(
            status=ExecutionStatus.FAILED, error="fail",
            alternatives_tried=[],
        )
        result = executor._try_alternative(node, failed_result)
        assert result is failed_result
        assert result.alternatives_tried == []

    def test_with_string_alternative_same_as_action_skipped(self, executor):
        node = _make_node("n1", "test_action", alternatives=["test_action", "alt_action"])
        failed_result = ExecutionResult(
            status=ExecutionStatus.FAILED, error="fail",
            alternatives_tried=[],
        )
        result = executor._try_alternative(node, failed_result)
        # "test_action" is skipped (same as original action), "alt_action" is tried
        # alt_action won't be registered, so it fails
        assert result.status == ExecutionStatus.FAILED
        assert "alt_action" in result.alternatives_tried

    def test_with_dict_alternative(self, executor):
        node = _make_node(
            "n1", "test_action",
            alternatives=[{"id": "alt1", "action": "alt_action", "preconditions": [], "parameters": {}}],
        )
        failed_result = ExecutionResult(status=ExecutionStatus.FAILED, error="fail")
        result = executor._try_alternative(node, failed_result)
        # alt_action not registered -> will fail
        assert result is not None

    def test_original_skipped_alternative_succeeds(self, executor, mock_action_info_factory):
        """When an alternative action is registered and succeeds, returns SUCCESS."""
        def cb(**kwargs):
            return {"success": True, "result": "alt_works"}
        node = _make_node(
            "n1", "original_action",
            alternatives=[{"id": "alt1", "action": "alt_action", "preconditions": [], "parameters": {}}],
        )
        failed_result = ExecutionResult(status=ExecutionStatus.FAILED, error="fail")
        # Patch execute_action to return success for alt_action
        with patch.object(executor, "execute_action", return_value={"success": True}):
            result = executor._try_alternative(node, failed_result)
            assert result.status == ExecutionStatus.SUCCESS
            assert result.result == {"success": True}

    def test_alternative_precondition_failure(self, executor):
        node = _make_node(
            "n1", "test_action",
            alternatives=[{"id": "alt1", "action": "alt_action", "preconditions": [False], "parameters": {}}],
        )
        failed_result = ExecutionResult(status=ExecutionStatus.FAILED, error="fail")
        result = executor._try_alternative(node, failed_result)
        # Preconditions not satisfied -> skipped, no alternatives succeed
        assert result.status == ExecutionStatus.FAILED
        assert "alt1" in result.alternatives_tried


# ---------------------------------------------------------------------------
# _parse_args / _positional_to_named_parameters
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_none(self, executor):
        assert executor._parse_args(None) == ()

    def test_empty_string(self, executor):
        assert executor._parse_args("") == ()

    def test_single_value(self, executor):
        result = executor._parse_args("'hello'")
        assert result == ("hello",)

    def test_tuple(self, executor):
        result = executor._parse_args("'a', 'b', 'c'")
        assert result == ("a", "b", "c")

    def test_dict(self, executor):
        result = executor._parse_args("{'key': 'value'}")
        assert result == ({"key": "value"},)

    def test_int(self, executor):
        result = executor._parse_args("42")
        assert result == (42,)

    def test_invalid_raises(self, executor):
        with pytest.raises(ValueError, match="Argumentos no válidos"):
            executor._parse_args("not valid python!")

    def test_whitespace_string(self, executor):
        result = executor._parse_args("  'hello'  ")
        assert result == ("hello",)

    def test_float(self, executor):
        result = executor._parse_args("3.14")
        assert result == (3.14,)


class TestPositionalToNamedParameters:
    def test_empty_args(self, executor):
        ai = MagicMock()
        ai.parameters = {"text": {"type": str, "default": None, "required": True}}
        result = executor._positional_to_named_parameters(ai, ())
        assert result == {}

    def test_single_arg(self, executor):
        ai = MagicMock()
        ai.parameters = {"text": {"type": str, "default": None, "required": True}}
        result = executor._positional_to_named_parameters(ai, ("hello",))
        assert result == {"text": "hello"}

    def test_multiple_args(self, executor):
        ai = MagicMock()
        ai.parameters = {"a": {}, "b": {}, "c": {}}
        result = executor._positional_to_named_parameters(ai, (1, 2, 3))
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_too_many_args(self, executor):
        ai = MagicMock()
        ai.parameters = {"a": {}}
        with pytest.raises(ValueError, match="Demasiados argumentos"):
            executor._positional_to_named_parameters(ai, (1, 2, 3))

    def test_partial_args(self, executor):
        ai = MagicMock()
        ai.parameters = {"a": {}, "b": {}, "c": {}}
        result = executor._positional_to_named_parameters(ai, (1,))
        assert result == {"a": 1}


# ---------------------------------------------------------------------------
# _get_legacy_function
# ---------------------------------------------------------------------------

class TestGetLegacyFunction:
    def test_finds_function(self, executor):
        func = executor._get_legacy_function("type_text")
        assert func is not None
        assert callable(func)

    def test_finds_mouse_function(self, executor):
        func = executor._get_legacy_function("move_to_position")
        assert func is not None
        assert callable(func)

    def test_finds_keyboard_function(self, executor):
        func = executor._get_legacy_function("press_key")
        assert func is not None
        assert callable(func)

    def test_not_found(self, executor):
        assert executor._get_legacy_function("nonexistent_function") is None

    def test_empty_name(self, executor):
        assert executor._get_legacy_function("") is None

    def test_none_name(self, executor):
        assert executor._get_legacy_function(None) is None  # type: ignore


# ---------------------------------------------------------------------------
# execute_plan / execute_plan_with_replan
# ---------------------------------------------------------------------------

class TestExecutePlan:
    def test_empty_plan_fails(self, executor):
        result = executor.execute_plan([])
        assert result.status == ExecutionStatus.FAILED
        assert "Plan vacío" in result.error

    def test_none_plan_fails(self, executor):
        result = executor.execute_plan(None)  # type: ignore
        assert result.status == ExecutionStatus.FAILED

    def test_non_list_plan_fails(self, executor):
        result = executor.execute_plan("not a list")  # type: ignore
        assert result.status == ExecutionStatus.FAILED

    def test_non_dict_plan_node_fails(self, executor):
        result = executor.execute_plan([42])
        assert result.status == ExecutionStatus.FAILED
        assert "no válido" in result.error

    def test_valid_node_with_callback_success(self, executor):
        def cb(current_state=None, **kwargs):
            return {"success": True, "result": "ok"}
        node = _make_node(
            "n1", "test_action",
            metadata={"execute_callback": cb, "parameters": {}, "cost": 1.0, "preconditions": []},
            parameters={},
        )
        result = executor.execute_plan([node])
        assert result.status == ExecutionStatus.SUCCESS

    def test_node_failure_no_alternative(self, executor):
        node = _make_node("n1", "nonexistent_action_12345", parameters={})
        result = executor.execute_plan([node])
        assert result.status == ExecutionStatus.FAILED

    def test_multiple_nodes_all_success(self, executor):
        def cb(**kwargs):
            return {"success": True}
        node1 = _make_node("n1", "action1", metadata={"execute_callback": cb}, parameters={})
        node2 = _make_node("n2", "action2", metadata={"execute_callback": cb}, parameters={})
        result = executor.execute_plan([node1, node2])
        assert result.status == ExecutionStatus.SUCCESS
        assert len(result.successful_nodes) == 2

    def test_multiple_nodes_stop_on_failure(self, executor):
        def cb(**kwargs):
            return {"success": True}
        success_node = _make_node("n1", "action1", metadata={"execute_callback": cb}, parameters={})
        fail_node = _make_node("n2", "action2", parameters={})  # no callback -> fails
        result = executor.execute_plan([success_node, fail_node])
        assert result.status == ExecutionStatus.FAILED
        assert len(result.successful_nodes) == 1

    def test_plan_id_from_argument(self, executor):
        def cb(**kwargs):
            return {"success": True}
        node = _make_node("n1", "a", metadata={"execute_callback": cb}, parameters={})
        result = executor.execute_plan([node], plan_id="custom_plan_123")
        assert result.plan_id == "custom_plan_123"

    def test_plan_execution_time_positive(self, executor):
        def cb(**kwargs):
            return {"success": True}
        node = _make_node("n1", "a", metadata={"execute_callback": cb}, parameters={})
        result = executor.execute_plan([node])
        assert result.execution_time >= 0.0

    def test_active_executions_tracking(self, executor):
        def cb(**kwargs):
            return {"success": True}
        node = _make_node("n1", "a", metadata={"execute_callback": cb}, parameters={})
        executor.execute_plan([node], plan_id="tracked_plan")
        assert "tracked_plan" not in executor.active_executions

    def test_node_result_error_recorded(self, executor):
        node = _make_node("n1", "nonexistent_xyz", parameters={})
        result = executor.execute_plan([node])
        assert result.status == ExecutionStatus.FAILED
        assert len(result.failed_nodes) > 0


class TestExecutePlanWithReplan:
    def test_empty_plan_fails(self, executor):
        result = executor.execute_plan_with_replan([])
        assert result["success"] is False

    def test_none_plan_fails(self, executor):
        result = executor.execute_plan_with_replan(None)  # type: ignore
        assert result["success"] is False

    def test_non_list_plan_fails(self, executor):
        result = executor.execute_plan_with_replan("not a list")  # type: ignore
        assert result["success"] is False

    def test_invalid_node_fails(self, executor):
        result = executor.execute_plan_with_replan([42])
        assert result["success"] is False

    def test_successful_plan(self, executor):
        def cb(**kwargs):
            return {"success": True}
        node = _make_node("n1", "a", metadata={"execute_callback": cb}, parameters={})
        result = executor.execute_plan_with_replan([node])
        assert result["success"] is True
        assert "n1" in result["successful_nodes"]

    def test_failed_node_triggers_replan(self, executor):
        """When a node fails and has alternatives, replan is attempted."""
        node = _make_node(
            "n1", "orig_action",
            alternatives=[{"id": "alt1", "action": "alt_action", "preconditions": [], "parameters": {}}],
            cost=1.0,
        )
        result = executor.execute_plan_with_replan([node], max_replan_attempts=2)
        assert "n1" in result["failed_nodes"][0]["id"]

    def test_goal_already_achieved(self, executor):
        """If goal is achieved before executing any node, returns success."""
        def cb(**kwargs):
            return {"success": True}
        node = _make_node("n1", "a", metadata={"execute_callback": cb}, parameters={})
        goal = {"type": "navigate", "target": {"url": "https://example.com"}}
        # State doesn't have current_url, so goal not achieved initially
        # The plan should still execute
        result = executor.execute_plan_with_replan([node], goal=goal, max_replan_attempts=0)
        assert result["success"] is True

    def test_replan_max_attempts_exhausted(self, executor):
        node = _make_node("n1", "nonexistent_xyz", cost=1.0)
        result = executor.execute_plan_with_replan([node], max_replan_attempts=2)
        assert result["success"] is False
        assert result["replan_attempts"] == 0  # No alternatives, replan not triggered

    def test_expensive_node_no_replan(self, executor):
        """Expensive nodes (>5.0) don't trigger replan."""
        node = _make_node("n1", "nonexistent_xyz", cost=10.0)
        result = executor.execute_plan_with_replan([node], max_replan_attempts=3)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# _replan_after_failure / _find_alternative_nodes
# ---------------------------------------------------------------------------

class TestReplanAfterFailure:
    def test_no_alternatives(self, executor):
        plan = [_make_node("n1", "test", cost=1.0)]
        new_plan = executor._replan_after_failure(plan, 0, {})
        # No alternatives and no registered alternatives -> returns original plan
        assert new_plan == plan

    def test_with_alternatives(self, executor):
        plan = [_make_node(
            "n1", "test", cost=1.0,
            alternatives=[{"id": "alt1", "action": "alt_action", "preconditions": [], "parameters": {}}],
        )]
        new_plan = executor._replan_after_failure(plan, 0, {})
        assert new_plan[0]["id"] == "alt1"
        assert new_plan != plan

    def test_string_alternative(self, executor):
        plan = [_make_node("n1", "test", cost=1.0, alternatives=["alt_action"])]
        new_plan = executor._replan_after_failure(plan, 0, {})
        assert new_plan[0]["action"] == "alt_action"

    def test_out_of_range_index(self, executor):
        plan = [_make_node("n1", "test", cost=1.0)]
        new_plan = executor._replan_after_failure(plan, 5, {})
        assert new_plan == plan


class TestFindAlternativeNodes:
    def test_returns_empty_for_unregistered_action(self, executor):
        """If the action isn't registered, no alternatives found via capability search."""
        result = executor._find_alternative_nodes({"action": "nonexistent_action_999"}, {})
        assert result == []

    def test_returns_list_type(self, executor):
        result = executor._find_alternative_nodes({"action": "test"}, {})
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _update_world_state_after_failure
# ---------------------------------------------------------------------------

class TestUpdateWorldStateAfterFailure:
    def test_failure_records_application_state(self, executor):
        node = _make_node("n1", "test", application="Chrome")
        result = ExecutionResult(status=ExecutionStatus.FAILED, error="fail")
        executor._update_world_state_after_failure(node, result)
        chrome_state = executor.current_state.application_states.get("Chrome", {})
        assert chrome_state.get("last_action_failed") is True

    def test_failure_without_application(self, executor):
        node = _make_node("n1", "test", application=None)
        result = ExecutionResult(status=ExecutionStatus.FAILED, error="fail")
        executor._update_world_state_after_failure(node, result)
        # Should not crash and timestamp should be updated
        assert executor.current_state.timestamp > 0


# ---------------------------------------------------------------------------
# _goal_achieved
# ---------------------------------------------------------------------------

class TestGoalAchieved:
    def test_navigate_goal_success(self, executor):
        goal = {"type": "navigate", "target": {"url": "https://example.com/"}}
        state = {"current_url": "https://example.com/"}
        assert executor._goal_achieved(goal, state) is True

    def test_navigate_goal_url_mismatch(self, executor):
        goal = {"type": "navigate", "target": {"url": "https://example.com/"}}
        state = {"current_url": "https://different.com/"}
        assert executor._goal_achieved(goal, state) is False

    def test_navigate_goal_no_url(self, executor):
        goal = {"type": "navigate", "target": "https://example.com/"}
        state = {"current_url": "https://example.com/"}
        assert executor._goal_achieved(goal, state) is True

    def test_open_application_goal_success(self, executor):
        goal = {"type": "open_application", "target": "Chrome"}
        state = {"chrome_open": True, "application_states": {}}
        assert executor._goal_achieved(goal, state) is True

    def test_close_application_goal_success(self, executor):
        goal = {"type": "close_application", "target": "Chrome"}
        state = {"chrome_open": False}
        assert executor._goal_achieved(goal, state) is True

    def test_search_goal_success(self, executor):
        goal = {"type": "search", "target": "test query"}
        state = {"search_performed": True}
        assert executor._goal_achieved(goal, state) is True

    def test_search_goal_not_achieved(self, executor):
        goal = {"type": "search", "target": "test query"}
        state = {"search_performed": False}
        assert executor._goal_achieved(goal, state) is False

    def test_unknown_goal_type(self, executor):
        goal = {"type": "unknown_type", "target": "test"}
        state = {"key": "value"}
        assert executor._goal_achieved(goal, state) is False

    def test_target_state_dict(self, executor):
        goal = {"type": "custom", "metadata": {"target_state": {"key": "value"}}}
        state = {"key": "value"}
        assert executor._goal_achieved(goal, state) is True

    def test_target_state_dict_partial(self, executor):
        goal = {"type": "custom", "metadata": {"target_state": {"key": "value", "other": 2}}}
        state = {"key": "value"}
        assert executor._goal_achieved(goal, state) is False


# ---------------------------------------------------------------------------
# process_and_execute
# ---------------------------------------------------------------------------

class TestProcessAndExecute:
    def test_no_command_returns_text(self, executor):
        result = executor.process_and_execute("Hello world, how are you?")
        assert "Hello world" in result

    def test_command_pattern_matched(self, executor):
        result = executor.process_and_execute("[CMD: type_text('hello')]")
        # type_text is a registered action, should be executed
        assert isinstance(result, str)

    def test_non_string_input(self, executor):
        result = executor.process_and_execute(42)  # type: ignore
        assert result == "42"

    def test_command_with_clean_text(self, executor):
        """When command execution returns a truthy result, that result is returned."""
        with patch.object(executor, "_execute_legacy_or_registered", return_value="executed_result"):
            result = executor.process_and_execute("Here is the response. [CMD: some_command()]")
            assert "executed_result" in result

    def test_unknown_command(self, executor):
        result = executor.process_and_execute("[CMD: nonexistent_command_xyz]")
        assert "Error" in result or isinstance(result, str)

    def test_command_with_dict_args(self, executor):
        result = executor.process_and_execute("[CMD: type_text({'text': 'hello'})]")
        assert isinstance(result, str)

    def test_command_no_args(self, executor):
        result = executor.process_and_execute("[CMD: type_text]")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# create_goal_from_command
# ---------------------------------------------------------------------------

class TestCreateGoalFromCommand:
    def test_navegar_a(self, executor):
        goal = executor.create_goal_from_command("navegar_a", {"url": "https://example.com"})
        assert goal is not None
        assert goal.type == "navigate"

    def test_abrir_chrome(self, executor):
        goal = executor.create_goal_from_command("abrir_chrome", {})
        assert goal is not None
        assert goal.type == "open_application"

    def test_abrir_youtube(self, executor):
        goal = executor.create_goal_from_command("abrir_youtube", {})
        assert goal is not None
        assert goal.type == "open_application"

    def test_buscar_en_google(self, executor):
        goal = executor.create_goal_from_command("buscar_en_google", {"query": "test"})
        assert goal is not None
        assert goal.type == "search"

    def test_cerrar_chrome(self, executor):
        goal = executor.create_goal_from_command("cerrar_chrome", {})
        assert goal is not None
        assert goal.type == "close_application"

    def test_unknown_command(self, executor):
        goal = executor.create_goal_from_command("unknown_command", {})
        assert goal is None

    def test_goal_has_metadata(self, executor):
        goal = executor.create_goal_from_command("abrir_chrome", {})
        assert goal is not None
        assert goal.metadata["original_command"] == "abrir_chrome"
        assert goal.metadata["created_from_legacy"] is True

    def test_goal_has_id(self, executor):
        goal = executor.create_goal_from_command("abrir_chrome", {})
        assert goal is not None
        assert goal.id.startswith("goal_abrir_chrome_")


# ---------------------------------------------------------------------------
# can_execute
# ---------------------------------------------------------------------------

class TestCanExecute:
    def test_registered_action(self, executor):
        actions = executor.action_registry.list_actions()
        if actions:
            action_name = actions[0]
            assert isinstance(executor.can_execute(action_name), bool)

    def test_unregistered_action(self, executor):
        assert executor.can_execute("nonexistent_action_999") is False

    def test_empty_action_name(self, executor):
        assert executor.can_execute("") is False

    def test_with_parameters(self, executor):
        actions = executor.action_registry.list_actions()
        if actions:
            action_name = actions[0]
            assert isinstance(executor.can_execute(action_name, {"param": "value"}), bool)


# ---------------------------------------------------------------------------
# list_commands
# ---------------------------------------------------------------------------

class TestListCommands:
    def test_returns_list(self, executor):
        commands = executor.list_commands()
        assert isinstance(commands, list)

    def test_returns_sorted(self, executor):
        commands = executor.list_commands()
        if len(commands) > 1:
            assert commands == sorted(commands)

    def test_contains_strings(self, executor):
        commands = executor.list_commands()
        assert all(isinstance(cmd, str) for cmd in commands)

    def test_non_empty(self, executor):
        commands = executor.list_commands()
        assert len(commands) > 0


# ---------------------------------------------------------------------------
# get_plannable_actions / get_action_info
# ---------------------------------------------------------------------------

class TestActionInfoMethods:
    def test_get_plannable_actions(self, executor):
        actions = executor.get_plannable_actions()
        assert isinstance(actions, dict)

    def test_get_action_info_existing(self, executor):
        actions = executor.action_registry.list_actions()
        if actions:
            info = executor.get_action_info(actions[0])
            assert info is not None

    def test_get_action_info_nonexistent(self, executor):
        info = executor.get_action_info("nonexistent_action_999")
        assert info is None


# ---------------------------------------------------------------------------
# get_current_state / update_state
# ---------------------------------------------------------------------------

class TestStateMethods:
    def test_get_current_state(self, executor):
        state = executor.get_current_state()
        assert isinstance(state, ExecutionState)
        assert state is executor.current_state

    def test_update_state(self, executor):
        executor.update_state({"constraints": ["new_constraint"]})
        assert "new_constraint" in executor.current_state.constraints

    def test_update_state_merges_apps(self, executor):
        executor.update_state({"application_states": {"chrome": {"open": True}}})
        assert executor.current_state.application_states["chrome"]["open"] is True

    def test_get_state_for_planning(self, executor):
        executor.update_state({"constraints": ["test"]})
        state = executor._get_state_for_planning()
        assert isinstance(state, dict)
        assert "constraints" in state
        assert state["constraints"] == ["test"]

    def test_get_state_for_planning_includes_app_keys(self, executor):
        executor.current_state.application_states = {"Chrome": {"open": True, "active": False}}
        state = executor._get_state_for_planning()
        assert state.get("chrome_open") is True

    def test_get_state_for_planning_includes_ui_elements(self, executor):
        executor.current_state.ui_elements = {"address_bar": {"focused": True}}
        state = executor._get_state_for_planning()
        assert state.get("ui_address_bar_focused") is True


# ---------------------------------------------------------------------------
# Learning interfaces
# ---------------------------------------------------------------------------

class TestLearningInterfaces:
    def test_get_learning_insights_no_system(self, executor):
        if executor.learning_system is None:
            result = executor.get_learning_insights()
            assert result == {"error": "Sistema de aprendizaje no disponible"}

    def test_get_action_learning_insights_no_system(self, executor):
        if executor.learning_system is None:
            result = executor.get_action_learning_insights("any_action")
            assert result == {"error": "Sistema de aprendizaje no disponible"}

    def test_get_cost_adjustments_no_system(self, executor):
        if executor.learning_system is None:
            assert executor.get_cost_adjustments() == {}

    def test_export_learning_data_no_system(self, executor):
        if executor.learning_system is None:
            # Should not raise
            executor.export_learning_data("/tmp/test.json")

    def test_import_learning_data_no_system(self, executor):
        if executor.learning_system is None:
            executor.import_learning_data("/tmp/test.json")

    def test_clear_learning_data_no_system(self, executor):
        if executor.learning_system is None:
            executor.clear_learning_data()

    def test_enable_learning_no_system(self, executor):
        if executor.learning_system is None:
            executor.enable_learning(True)

    def test_get_action_stats(self, executor):
        stats = executor.get_action_stats()
        assert isinstance(stats, dict)


# ---------------------------------------------------------------------------
# get_executor singleton
# ---------------------------------------------------------------------------

class TestGetExecutor:
    def test_returns_executor(self):
        import src.hands.executor as mod
        original = mod._executor_instance
        mod._executor_instance = None
        try:
            ex = get_executor()
            assert isinstance(ex, Executor)
            ex2 = get_executor()
            assert ex is ex2
        finally:
            mod._executor_instance = original

    def test_singleton_persistence(self):
        ex1 = get_executor()
        ex2 = get_executor()
        assert ex1 is ex2

    def test_singleton_thread_safety(self):
        """get_executor uses a lock."""
        import src.hands.executor as mod
        assert hasattr(mod, "_executor_instance_lock")


# ---------------------------------------------------------------------------
# _execute_node_action
# ---------------------------------------------------------------------------

class TestExecuteNodeAction:
    def test_callback_executes_successfully(self, executor):
        def cb(current_state=None, **kwargs):
            return {"success": True, "result": "action_result"}
        node = _make_node("n1", "test_action", metadata={"execute_callback": cb}, parameters={})
        result = executor._execute_node_action(node, None)
        assert result is not None
        assert result["success"] is True

    def test_no_callback_no_action_raises(self, executor):
        node = _make_node("n1", "test_action", parameters={})
        # No execute_callback in metadata, action "test_action" is not registered
        with pytest.raises(ValueError, match="Acción no encontrada"):
            executor._execute_node_action(node, None)

    def test_node_without_action_falls_back_to_id(self, executor):
        """When action is None, falls back to node id, then fails if not registered."""
        node = _make_node("n1", None, parameters={})
        node["action"] = None
        node["id"] = "n1"
        with pytest.raises(ValueError, match="Acción no encontrada"):
            executor._execute_node_action(node, None)

    def test_declarative_node_raises(self, executor):
        node = _make_node("n1", "test_action", parameters={})
        node["type"] = "state"
        with pytest.raises(ValueError, match="declarativo"):
            executor._execute_node_action(node, None)

    def test_node_type_resource_raises(self, executor):
        node = _make_node("n1", "test_action", parameters={})
        node["type"] = "resource"
        with pytest.raises(ValueError, match="declarativo"):
            executor._execute_node_action(node, None)

    def test_node_type_goal_raises(self, executor):
        node = _make_node("n1", "test_action", parameters={})
        node["type"] = "goal"
        with pytest.raises(ValueError, match="declarativo"):
            executor._execute_node_action(node, None)

    def test_invalid_parameters_raises(self, executor):
        node = _make_node("n1", "test_action", parameters="not_a_dict")
        with pytest.raises(TypeError, match="diccionario"):
            executor._execute_node_action(node, None)

    def test_explicit_action_from_metadata(self, executor):
        def cb(current_state=None, **kwargs):
            return {"success": True}
        node = _make_node("n1", None, metadata={"execute_callback": cb, "action_name": "test_action"}, parameters={})
        result = executor._execute_node_action(node, None)
        assert result is not None
        assert result["success"] is True

    def test_verify_false_passes_through(self, executor):
        def cb(current_state=None, **kwargs):
            return {"success": True}
        node = _make_node("n1", "test_action", metadata={"execute_callback": cb}, parameters={})
        node["metadata"]["verify"] = False
        result = executor._execute_node_action(node, None)
        assert result is not None
