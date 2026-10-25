# -*- coding: utf-8 -*-
"""Tests para TaskExecutor y tipos relacionados (src/hands/planner/task_executor.py).

Cubre:
- Enums TaskExecutorStatus, TaskExecutionMode
- Dataclass TaskExecutionConfig (normalización de valores)
- Métodos estáticos: _task_metadata, _task_application, _task_parameters,
  _normalize_execution_result, _truthy_success, _as_list, _normalize_key,
  _safe_number, _evaluate_precondition, _signature_accepts, _call_callback
- Métodos de instancia: _calculate_task_cost, _resolve_action_name,
  _check_task_preconditions, _should_execute_conditionally,
  _convert_task_to_node, _create_execution_callback, _create_success_criteria,
  _execute_node, _apply_result_to_state, _try_alternative,
  execute_task, execute_task_with_retry, execute_task_hierarchy (modos),
  get_execution_statistics, _update_execution_statistics, legacy capability handlers
- Singleton get_task_executor

El StructuredLogger de proyecto carece de ``exception``; se parcha para que
las rutas que capturan excepciones no fallen con AttributeError.
"""

import inspect
import math
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.hands.planner.htn_manager import TaskExecutionResult
from src.hands.planner.node import NodeType, Task, TaskStatus
from src.hands.planner.task_executor import (
    TaskExecutionConfig,
    TaskExecutor,
    TaskExecutionMode,
    TaskExecutorStatus,
    get_task_executor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id="t1", **kwargs):
    """Crea una Task con atributos dinámicos (metadata, parameters, application)."""
    task = Task(id=task_id, name=kwargs.pop("name", task_id), description=kwargs.pop("description", ""))
    task.metadata = kwargs.pop("metadata", {})
    task.parameters = kwargs.pop("parameters", {})
    task.application = kwargs.pop("application", None)
    task.dependencies = kwargs.pop("dependencies", [])
    return task


@pytest.fixture
def patched_logger():
    """Patch logger.exception on the task_executor module since StructuredLogger lacks it."""
    with patch("src.hands.planner.task_executor.logger") as mock_logger:
        mock_logger.exception = lambda *a, **kw: None
        mock_logger.info = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.debug = MagicMock()
        mock_logger.error = MagicMock()
        yield mock_logger


@pytest.fixture
def executor(patched_logger):
    """Crea un TaskExecutor aislado con el logger parcheado."""
    return TaskExecutor()


# ---------------------------------------------------------------------------
# Enums y dataclasses
# ---------------------------------------------------------------------------

class TestTaskExecutorStatus:
    def test_values(self):
        assert TaskExecutorStatus.IDLE.value == "idle"
        assert TaskExecutorStatus.PREPARING.value == "preparing"
        assert TaskExecutorStatus.EXECUTING.value == "executing"
        assert TaskExecutorStatus.COMPLETED.value == "completed"
        assert TaskExecutorStatus.FAILED.value == "failed"
        assert TaskExecutorStatus.RETRYING.value == "retrying"

    def test_all_distinct(self):
        values = [e.value for e in TaskExecutorStatus]
        assert len(values) == len(set(values))


class TestTaskExecutionMode:
    def test_values(self):
        assert TaskExecutionMode.SEQUENTIAL.value == "sequential"
        assert TaskExecutionMode.PARALLEL.value == "parallel"
        assert TaskExecutionMode.CONDITIONAL.value == "conditional"
        assert TaskExecutionMode.FALLBACK.value == "fallback"

    def test_all_distinct(self):
        values = [e.value for e in TaskExecutionMode]
        assert len(values) == len(set(values))


class TestTaskExecutionConfig:
    def test_defaults(self):
        config = TaskExecutionConfig()
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.timeout_per_task == 30.0
        assert config.enable_fallback is True
        assert config.parallel_execution is False
        assert config.log_execution_details is True

    def test_post_init_clamps_negatives(self):
        config = TaskExecutionConfig(max_retries=-5, retry_delay=-1.0, timeout_per_task=-10.0)
        assert config.max_retries == 0
        assert config.retry_delay == 0.0
        assert config.timeout_per_task == 0.0

    def test_post_init_coerces_strings_to_bool(self):
        config = TaskExecutionConfig(enable_fallback="yes", parallel_execution="", log_execution_details="true")
        assert config.enable_fallback is True
        assert config.parallel_execution is False
        assert config.log_execution_details is True

    def test_post_init_invalid_strings_use_defaults(self):
        config = TaskExecutionConfig(max_retries="abc", retry_delay="xyz", timeout_per_task=None)
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.timeout_per_task == 30.0

    def test_post_init_finite_check(self):
        config = TaskExecutionConfig(timeout_per_task=float("inf"))
        assert config.timeout_per_task == 30.0

    def test_post_init_clamps_negative_floats(self):
        config = TaskExecutionConfig(retry_delay=-0.5)
        assert config.retry_delay == 0.0

    def test_post_init_clamps_negative_ints(self):
        config = TaskExecutionConfig(timeout_per_task=-100.0)
        assert config.timeout_per_task == 0.0

    @staticmethod
    def test_safe_int():
        assert TaskExecutionConfig._safe_int(5, 3) == 5
        assert TaskExecutionConfig._safe_int("abc", 3) == 3
        assert TaskExecutionConfig._safe_int(None, 3) == 3
        assert TaskExecutionConfig._safe_int(True, 3) == 1

    @staticmethod
    def test_safe_int_negative():
        assert TaskExecutionConfig._safe_int(-5, 3) == -5

    @staticmethod
    def test_safe_float():
        assert TaskExecutionConfig._safe_float(5.0, 1.0) == 5.0
        assert TaskExecutionConfig._safe_float("abc", 1.0) == 1.0
        assert TaskExecutionConfig._safe_float(float("inf"), 1.0) == 1.0
        assert TaskExecutionConfig._safe_float(None, 1.0) == 1.0


# ---------------------------------------------------------------------------
# TaskExecutor initialization
# ---------------------------------------------------------------------------

class TestTaskExecutorInit:
    def test_default_config(self, executor):
        assert isinstance(executor.config, TaskExecutionConfig)
        assert executor.status == TaskExecutorStatus.IDLE
        assert executor.current_task is None
        assert isinstance(executor.execution_context, dict)
        assert executor.total_executions == 0
        assert executor.successful_executions == 0
        assert executor.failed_executions == 0
        assert executor.total_attempts == 0
        assert executor.average_execution_time == 0.0

    def test_custom_config(self, patched_logger):
        config = TaskExecutionConfig(max_retries=5, enable_fallback=False, parallel_execution=True)
        te = TaskExecutor(config=config)
        assert te.config.max_retries == 5
        assert te.config.enable_fallback is False
        assert te.config.parallel_execution is True

    def test_safe_get_returns_none_on_failure(self, patched_logger):
        with patch(
            "src.hands.planner.task_executor.get_htn_manager",
            side_effect=RuntimeError("boom"),
        ):
            te = TaskExecutor()
            assert te.htn_manager is None

    def test_safe_get_returns_value_on_success(self, patched_logger):
        mock_manager = MagicMock()
        with patch("src.hands.planner.task_executor.get_htn_manager", return_value=mock_manager):
            te = TaskExecutor()
            assert te.htn_manager is mock_manager

    def test_statistics_initial(self, executor):
        stats = executor.get_execution_statistics()
        assert stats["status"] == "idle"
        assert stats["total_executions"] == 0
        assert stats["total_attempts"] == 0
        assert stats["successful_executions"] == 0
        assert stats["failed_executions"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["average_execution_time"] == 0.0
        assert stats["current_task"] is None


# ---------------------------------------------------------------------------
# Static helper methods
# ---------------------------------------------------------------------------

class TestTaskExecutorStaticHelpers:
    def test_task_metadata_with_dict(self):
        task = _make_task(metadata={"action": "foo", "cost": 3.0})
        assert TaskExecutor._task_metadata(task) == {"action": "foo", "cost": 3.0}

    def test_task_metadata_without_attribute(self):
        task = Task(id="t", name="t", description="")
        assert TaskExecutor._task_metadata(task) == {}

    def test_task_metadata_non_dict(self):
        task = SimpleNamespace(id="t", name="t", metadata="not a dict")
        assert TaskExecutor._task_metadata(task) == {}

    def test_task_application_from_metadata(self):
        task = _make_task(metadata={"application": "Chrome"})
        assert TaskExecutor._task_application(task) == "Chrome"

    def test_task_application_fallback_to_attribute(self):
        task = SimpleNamespace(id="t", name="t", metadata={}, application="Firefox")
        assert TaskExecutor._task_application(task) == "Firefox"

    def test_task_application_none(self):
        task = _make_task()
        assert TaskExecutor._task_application(task) is None

    def test_task_application_strips_whitespace(self):
        task = _make_task(metadata={"application": "  Chrome  "})
        assert TaskExecutor._task_application(task) == "Chrome"

    def test_task_parameters_from_metadata(self):
        task = _make_task(metadata={"parameters": {"url": "https://example.com"}})
        assert TaskExecutor._task_parameters(task) == {"url": "https://example.com"}

    def test_task_parameters_from_attribute(self):
        task = _make_task(parameters={"query": "test"})
        assert TaskExecutor._task_parameters(task) == {"query": "test"}

    def test_task_parameters_both_merge(self):
        task = _make_task(parameters={"a": 1}, metadata={"parameters": {"b": 2}})
        params = TaskExecutor._task_parameters(task)
        assert params == {"a": 1, "b": 2}

    def test_task_parameters_no_params(self):
        task = _make_task()
        assert TaskExecutor._task_parameters(task) == {}

    def test_as_list_none(self):
        assert TaskExecutor._as_list(None) == []

    def test_as_list_various(self):
        assert TaskExecutor._as_list([1, 2]) == [1, 2]
        assert TaskExecutor._as_list((1, 2)) == [1, 2]
        result = TaskExecutor._as_list({1, 2})
        assert set(result) == {1, 2}
        assert TaskExecutor._as_list("hello") == ["hello"]
        assert TaskExecutor._as_list(42) == [42]

    def test_as_list_empty_tuple(self):
        assert TaskExecutor._as_list(()) == []

    def test_normalize_key_normal(self):
        assert TaskExecutor._normalize_key("Chrome") == "chrome"

    def test_normalize_key_spaces(self):
        assert TaskExecutor._normalize_key("My App Name") == "my_app_name"

    def test_normalize_key_none(self):
        assert TaskExecutor._normalize_key(None) == ""

    def test_normalize_key_empty(self):
        assert TaskExecutor._normalize_key("") == ""

    def test_safe_number_float(self):
        assert TaskExecutor._safe_number(5.0) == 5.0

    def test_safe_number_invalid(self):
        assert TaskExecutor._safe_number("abc") == 0.0

    def test_safe_number_none(self):
        assert TaskExecutor._safe_number(None) == 0.0

    def test_safe_number_default(self):
        assert TaskExecutor._safe_number("abc", default=99.0) == 99.0

    def test_safe_number_inf(self):
        assert TaskExecutor._safe_number(float("inf")) == 0.0

    def test_safe_number_zero(self):
        assert TaskExecutor._safe_number(0) == 0.0

    def test_safe_number_nan(self):
        assert TaskExecutor._safe_number(float("nan")) == 0.0

    def test_signature_accepts_matching(self):
        def func(a, b, c=None):
            pass
        sig = inspect.signature(func)
        assert TaskExecutor._signature_accepts(sig, (1, 2), {})

    def test_signature_accepts_with_kwargs(self):
        def func(a, b=None, **kwargs):
            pass
        sig = inspect.signature(func)
        assert TaskExecutor._signature_accepts(sig, (), {"a": 1, "b": 2, "extra": 3})

    def test_signature_rejects_non_matching(self):
        def func(a, b):
            pass
        sig = inspect.signature(func)
        assert not TaskExecutor._signature_accepts(sig, (1, 2, 3), {})

    def test_call_callback_direct_call(self):
        def cb(text):
            return {"success": True, "result": f"got {text}"}
        sig = inspect.signature(cb)
        result = TaskExecutor._call_callback(cb, {"text": "hello"})
        assert result["success"] is True
        assert result["result"] == "got hello"

    def test_call_callback_single_arg_fallback(self):
        def cb(ctx):
            return {"success": True, "result": ctx}
        result = TaskExecutor._call_callback(cb, {"current_state": {"x": 1}})
        assert result["success"] is True
        assert result["result"]["current_state"]["x"] == 1

    def test_call_callback_incompatible_signature(self):
        def cb(a, b, c):
            pass
        result = TaskExecutor._call_callback(cb, {"extra": "data"})
        assert result["success"] is False
        assert "no acepta" in result["error"]


# ---------------------------------------------------------------------------
# _normalize_execution_result / _truthy_success
# ---------------------------------------------------------------------------

class TestNormalizeExecutionResult:
    def test_task_execution_result(self):
        ter = TaskExecutionResult(
            task_id="t1", status=TaskStatus.COMPLETED, result={"x": 1}, execution_time=1.0
        )
        normalized = TaskExecutor._normalize_execution_result(ter)
        assert normalized["success"] is True
        assert normalized["result"] == {"x": 1}
        assert normalized["execution_time"] == 1.0
        assert normalized["error"] is None

    def test_task_execution_result_failed(self):
        ter = TaskExecutionResult(task_id="t1", status=TaskStatus.FAILED, error_message="boom")
        normalized = TaskExecutor._normalize_execution_result(ter)
        assert normalized["success"] is False
        assert normalized["error"] == "boom"

    def test_dict_with_success_true(self):
        normalized = TaskExecutor._normalize_execution_result({"success": True, "result": "ok"})
        assert normalized["success"] is True
        assert normalized["result"] == "ok"

    def test_dict_with_success_false(self):
        normalized = TaskExecutor._normalize_execution_result({"success": False, "error": "fail"})
        assert normalized["success"] is False
        assert normalized["error"] == "fail"

    def test_dict_with_status_success(self):
        normalized = TaskExecutor._normalize_execution_result({"status": "success", "data": "test"})
        assert normalized["success"] is True

    def test_dict_with_status_failed(self):
        normalized = TaskExecutor._normalize_execution_result({"status": "failed"})
        assert normalized["success"] is False

    def test_dict_success_as_string_true(self):
        normalized = TaskExecutor._normalize_execution_result({"success": "true"})
        assert normalized["success"] is True

    def test_dict_success_as_string_false(self):
        normalized = TaskExecutor._normalize_execution_result({"success": "false"})
        assert normalized["success"] is False

    def test_dict_no_success_no_status(self):
        normalized = TaskExecutor._normalize_execution_result({"data": "test"})
        assert normalized["success"] is False

    def test_bool_true(self):
        assert TaskExecutor._normalize_execution_result(True) == {"success": True}

    def test_bool_false(self):
        assert TaskExecutor._normalize_execution_result(False) == {"success": False}

    def test_none(self):
        normalized = TaskExecutor._normalize_execution_result(None)
        assert normalized["success"] is False
        assert "error" in normalized

    def test_object_with_success_attr(self):
        obj = SimpleNamespace(success=True)
        normalized = TaskExecutor._normalize_execution_result(obj)
        assert normalized["success"] is True

    def test_object_with_status_attr(self):
        obj = SimpleNamespace(status="completed")
        normalized = TaskExecutor._normalize_execution_result(obj)
        assert normalized["success"] is True

    def test_object_without_status(self):
        obj = SimpleNamespace(data="test")
        normalized = TaskExecutor._normalize_execution_result(obj)
        assert normalized["success"] is False
        assert normalized["result"] is obj


class TestTruthySuccess:
    def test_bool_true(self):
        assert TaskExecutor._truthy_success(True) is True

    def test_bool_false(self):
        assert TaskExecutor._truthy_success(False) is False

    def test_int_nonzero(self):
        assert TaskExecutor._truthy_success(1) is True

    def test_int_zero(self):
        assert TaskExecutor._truthy_success(0) is False

    def test_float_nonzero(self):
        assert TaskExecutor._truthy_success(3.14) is True

    def test_str_true(self):
        assert TaskExecutor._truthy_success("true") is True

    def test_str_completed(self):
        assert TaskExecutor._truthy_success("completed") is True

    def test_str_yes(self):
        assert TaskExecutor._truthy_success("yes") is True

    def test_str_ok(self):
        assert TaskExecutor._truthy_success("ok") is True

    def test_str_no(self):
        assert TaskExecutor._truthy_success("no") is False

    def test_str_empty(self):
        assert TaskExecutor._truthy_success("") is False

    def test_str_random(self):
        assert TaskExecutor._truthy_success("random") is False

    def test_none(self):
        assert TaskExecutor._truthy_success(None) is False

    def test_str_1(self):
        assert TaskExecutor._truthy_success("1") is True

    def test_str_0(self):
        assert TaskExecutor._truthy_success("0") is False


# ---------------------------------------------------------------------------
# _resolve_action_name / _calculate_task_cost
# ---------------------------------------------------------------------------

class TestResolveActionName:
    def test_from_metadata_action(self, executor):
        task = _make_task(metadata={"action": "my_action"})
        assert executor._resolve_action_name(task) == "my_action"

    def test_from_metadata_action_name(self, executor):
        task = _make_task(metadata={"action_name": "alt_action"})
        assert executor._resolve_action_name(task) == "alt_action"

    def test_fallback_to_task_id(self, executor):
        task = _make_task()
        result = executor._resolve_action_name(task)
        assert result == task.id

    def test_fallback_to_metadata_capability(self, executor):
        task = _make_task(metadata={"capability": "search"})
        result = executor._resolve_action_name(task)
        assert result == "search"

    def test_strips_whitespace(self, executor):
        task = _make_task(metadata={"action": "  spaced_action  "})
        assert executor._resolve_action_name(task) == "spaced_action"

    def test_priority_order(self, executor):
        """action takes priority over action_name and capability."""
        task = _make_task(metadata={"action": "primary", "action_name": "secondary", "capability": "ternary"})
        assert executor._resolve_action_name(task) == "primary"


class TestCalculateTaskCost:
    def test_explicit_cost(self, executor):
        task = _make_task(metadata={"cost": 5.0})
        assert executor._calculate_task_cost(task, {}) == 5.0

    def test_invalid_cost_falls_back(self, executor):
        task = _make_task(metadata={"cost": "abc"})
        cost = executor._calculate_task_cost(task, {})
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_no_explicit_cost_complexity_default(self, executor):
        task = _make_task()
        cost = executor._calculate_task_cost(task, {})
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_complexity_factor(self, executor):
        task = _make_task(metadata={"complexity": 3.0})
        cost = executor._calculate_task_cost(task, {})
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_complexity_with_app_open(self, executor):
        task = _make_task(metadata={"complexity": 4.0, "application": "Chrome"})
        state = {"chrome_open": True}
        # base_cost = 4.0, application "chrome", state has chrome_open=True -> 4.0 * 0.5 = 2.0
        # BUT wait: _calculate_task_cost checks `current_state.get(f"{application.lower()}_open", False)`
        # application = "Chrome", so it checks `current_state.get("chrome_open", False)`
        assert executor._calculate_task_cost(task, state) == 2.0

    def test_app_not_open_no_discount(self, executor):
        task = _make_task(metadata={"complexity": 4.0, "application": "Chrome"})
        assert executor._calculate_task_cost(task, {}) == 4.0

    def test_requires_ui_discount(self, executor):
        task = _make_task(metadata={"complexity": 4.0, "requires_ui": True})
        state = {"ui_resources_ready": True}
        # 4.0 * 0.8 = 3.2
        assert abs(executor._calculate_task_cost(task, state) - 3.2) < 1e-9

    def test_negative_cost_ignored(self, executor):
        task = _make_task(metadata={"cost": -5.0})
        # Negative cost -> invalid -> falls through to complexity default
        cost = executor._calculate_task_cost(task, {})
        assert cost == 1.0

    def test_estimated_cost_fallback(self, executor):
        task = _make_task(metadata={"estimated_cost": 7.0})
        assert executor._calculate_task_cost(task, {}) == 7.0

    def test_zero_cost_valid(self, executor):
        task = _make_task(metadata={"cost": 0.0})
        assert executor._calculate_task_cost(task, {}) == 0.0


# ---------------------------------------------------------------------------
# _evaluate_precondition (static)
# ---------------------------------------------------------------------------

class TestEvaluatePrecondition:
    def test_callable_true(self):
        assert TaskExecutor._evaluate_precondition(lambda s: True, {}) is True

    def test_callable_false(self):
        assert TaskExecutor._evaluate_precondition(lambda s: False, {}) is False

    def test_callable_exception(self):
        assert TaskExecutor._evaluate_precondition(lambda s: (_ for _ in ()).throw(RuntimeError()), {}) is False

    def test_string_key_exists(self):
        assert TaskExecutor._evaluate_precondition("flag", {"flag": True}) is True

    def test_string_key_missing(self):
        assert TaskExecutor._evaluate_precondition("flag", {}) is False

    def test_string_key_falsy(self):
        assert TaskExecutor._evaluate_precondition("flag", {"flag": False}) is False

    def test_dict_equals_match(self):
        assert TaskExecutor._evaluate_precondition({"key": "x", "equals": 5}, {"x": 5}) is True

    def test_dict_equals_mismatch(self):
        assert TaskExecutor._evaluate_precondition({"key": "x", "equals": 5}, {"x": 3}) is False

    def test_dict_value_match(self):
        assert TaskExecutor._evaluate_precondition({"key": "y", "value": 10}, {"y": 10}) is True

    def test_dict_value_mismatch(self):
        assert TaskExecutor._evaluate_precondition({"key": "y", "value": 10}, {"y": 5}) is False

    def test_dict_no_key(self):
        assert TaskExecutor._evaluate_precondition({"key": "nonexistent"}, {"x": 3}) is False

    def test_dict_truthy_key(self):
        assert TaskExecutor._evaluate_precondition({"key": "active"}, {"active": True}) is True

    def test_dict_expected_field(self):
        """TaskExecutor._evaluate_precondition does not check 'expected'; falls through to truthy check."""
        assert TaskExecutor._evaluate_precondition({"key": "count", "expected": 5}, {"count": 5}) is True

    def test_dict_expected_field_truthy(self):
        """When 'expected' is present but no 'equals'/'value', uses truthy key check."""
        assert TaskExecutor._evaluate_precondition({"key": "count", "expected": 5}, {"count": 3}) is True

    def test_unknown_condition_type(self):
        assert TaskExecutor._evaluate_precondition(42, {}) is False

    def test_string_with_spaces_not_stripped(self):
        """TaskExecutor._evaluate_precondition does not strip spaces from string conditions."""
        assert TaskExecutor._evaluate_precondition("  flag  ", {"flag": True}) is False
        assert TaskExecutor._evaluate_precondition("  flag  ", {"  flag  ": True}) is True


# ---------------------------------------------------------------------------
# _check_task_preconditions
# ---------------------------------------------------------------------------

class TestCheckTaskPreconditions:
    def test_no_preconditions(self, executor):
        task = _make_task()
        assert executor._check_task_preconditions(task, {}) is True

    def test_dependency_satisfied(self, executor):
        task = _make_task(dependencies=["dep1"])
        state = {"completed_tasks": ["dep1", "dep2"]}
        assert executor._check_task_preconditions(task, state) is True

    def test_dependency_not_satisfied(self, executor):
        task = _make_task(dependencies=["dep1"])
        state = {"completed_tasks": ["dep2"]}
        assert executor._check_task_preconditions(task, state) is False

    def test_no_dependencies(self, executor):
        task = _make_task()
        assert executor._check_task_preconditions(task, {}) is True

    def test_state_requirements_satisfied(self, executor):
        task = _make_task(metadata={"state_requirements": {"ready": True}})
        assert executor._check_task_preconditions(task, {"ready": True}) is True

    def test_state_requirements_not_satisfied(self, executor):
        task = _make_task(metadata={"state_requirements": {"ready": True}})
        assert executor._check_task_preconditions(task, {"ready": False}) is False

    def test_requires_ui_not_ready(self, executor):
        task = _make_task(metadata={"requires_ui": True})
        assert executor._check_task_preconditions(task, {"ui_resources_ready": False}) is False

    def test_requires_ui_ready(self, executor):
        task = _make_task(metadata={"requires_ui": True})
        assert executor._check_task_preconditions(task, {"ui_resources_ready": True}) is True

    def test_requires_ui_no_state(self, executor):
        task = _make_task(metadata={"requires_ui": True})
        assert executor._check_task_preconditions(task, {}) is False

    def test_string_precondition_satisfied(self, executor):
        task = _make_task(metadata={"preconditions": ["flag"]})
        assert executor._check_task_preconditions(task, {"flag": True}) is True

    def test_string_precondition_not_satisfied(self, executor):
        task = _make_task(metadata={"preconditions": ["flag"]})
        assert executor._check_task_preconditions(task, {}) is False

    def test_dict_precondition_satisfied(self, executor):
        task = _make_task(metadata={"preconditions": [{"key": "count", "equals": 5}]})
        assert executor._check_task_preconditions(task, {"count": 5}) is True

    def test_dict_precondition_not_satisfied(self, executor):
        task = _make_task(metadata={"preconditions": [{"key": "count", "equals": 5}]})
        assert executor._check_task_preconditions(task, {"count": 3}) is False

    def test_callable_precondition_satisfied(self, executor):
        task = _make_task(metadata={"preconditions": [lambda s: s.get("ready")]})
        assert executor._check_task_preconditions(task, {"ready": True}) is True

    def test_callable_precondition_not_satisfied(self, executor):
        task = _make_task(metadata={"preconditions": [lambda s: s.get("ready")]})
        assert executor._check_task_preconditions(task, {"ready": False}) is False

    def test_callable_precondition_exception(self, executor):
        task = _make_task(metadata={"preconditions": [lambda s: (_ for _ in ()).throw(RuntimeError())]})
        assert executor._check_task_preconditions(task, {}) is False

    def test_multiple_preconditions_all_pass(self, executor):
        task = _make_task(metadata={"preconditions": ["flag", {"key": "count", "equals": 5}]})
        assert executor._check_task_preconditions(task, {"flag": True, "count": 5}) is True

    def test_multiple_preconditions_one_fails(self, executor):
        task = _make_task(metadata={"preconditions": ["flag", {"key": "count", "equals": 5}]})
        assert executor._check_task_preconditions(task, {"flag": False, "count": 5}) is False

    def test_application_not_available_in_state(self, executor):
        task = _make_task(metadata={"application": "Chrome", "cost": 1.0})
        state = {"chrome_available": False}
        assert executor._check_task_preconditions(task, state) is False

    def test_application_available_in_state(self, executor):
        task = _make_task(metadata={"application": "Chrome", "cost": 1.0})
        state = {"chrome_available": True}
        assert executor._check_task_preconditions(task, state) is True

    def test_application_not_available_in_app_states(self, executor):
        task = _make_task(metadata={"application": "MyApp", "cost": 1.0})
        state = {"application_states": {"MyApp": {"available": False}}}
        assert executor._check_task_preconditions(task, state) is False

    def test_application_available_in_app_states(self, executor):
        task = _make_task(metadata={"application": "MyApp", "cost": 1.0})
        state = {"application_states": {"MyApp": {"available": True}}}
        assert executor._check_task_preconditions(task, state) is True


# ---------------------------------------------------------------------------
# _convert_task_to_node
# ---------------------------------------------------------------------------

class TestConvertTaskToNode:
    def test_basic_conversion(self, executor):
        task = _make_task(
            metadata={
                "action": "test_action",
                "cost": 2.0,
                "preconditions": ["dep"],
                "effects": ["effect1"],
            }
        )
        node = executor._convert_task_to_node(task, {})
        assert node is not None
        assert node.id == task.id
        assert node.name == task.name
        assert node.type == NodeType.ACTION
        assert node.cost == 2.0
        assert node.preconditions == ["dep"]
        assert node.effects == ["effect1"]
        assert node.metadata["action_name"] == "test_action"
        assert node.metadata["task_id"] == task.id

    def test_conversion_without_metadata(self, executor):
        task = _make_task()
        node = executor._convert_task_to_node(task, {})
        assert node is not None
        assert node.id == task.id
        assert node.type == NodeType.ACTION
        assert node.cost == 1.0  # default cost

    def test_conversion_sets_callbacks(self, executor):
        task = _make_task(metadata={"action": "test_action"})
        node = executor._convert_task_to_node(task, {})
        assert callable(node.execute_callback)
        assert callable(node.success_criteria)

    def test_conversion_with_execute_callback(self, executor):
        def cb(**kwargs):
            return {"success": True, "result": "done"}
        task = _make_task(metadata={"execute_callback": cb})
        node = executor._convert_task_to_node(task, {})
        result = node.execute_callback(current_state={})
        assert result["success"] is True

    def test_conversion_with_node_type_condition(self, executor):
        task = _make_task(metadata={"node_type": "condition"})
        node = executor._convert_task_to_node(task, {})
        assert node.type == NodeType.CONDITION

    def test_conversion_invalid_node_type_defaults_to_action(self, executor):
        task = _make_task(metadata={"node_type": "bogus"})
        node = executor._convert_task_to_node(task, {})
        assert node.type == NodeType.ACTION

    def test_conversion_with_dependencies(self, executor):
        task = _make_task(metadata={"action": "test_action"}, dependencies=["dep1", "dep2"])
        node = executor._convert_task_to_node(task, {})
        assert node.dependencies == ["dep1", "dep2"]

    def test_conversion_with_parameters(self, executor):
        task = _make_task(metadata={"action": "test_action"}, parameters={"url": "https://example.com"})
        node = executor._convert_task_to_node(task, {})
        assert node.parameters == {"url": "https://example.com"}

    def test_conversion_with_application(self, executor):
        task = _make_task(metadata={"action": "test_action"}, application="Chrome")
        node = executor._convert_task_to_node(task, {})
        assert node.application == "Chrome"

    def test_conversion_with_state_requirements(self, executor):
        task = _make_task(metadata={"action": "test_action", "state_requirements": {"open": True}})
        node = executor._convert_task_to_node(task, {})
        assert node.state_requirements == {"open": True}

    def test_conversion_with_state_modifications(self, executor):
        task = _make_task(metadata={"action": "test_action", "state_modifications": {"open": True}})
        node = executor._convert_task_to_node(task, {})
        assert node.state_modifications == {"open": True}

    def test_conversion_with_ui_element(self, executor):
        task = _make_task(metadata={"action": "test_action", "ui_element": "address_bar"})
        node = executor._convert_task_to_node(task, {})
        assert node.metadata.get("ui_element") == "address_bar"

    def test_conversion_node_type_object(self, executor):
        task = _make_task(metadata={"node_type": NodeType.ACTION})
        node = executor._convert_task_to_node(task, {})
        assert node.type == NodeType.ACTION

    def test_conversion_handles_exception(self, executor, patched_logger):
        """If Node construction fails, returns None instead of crashing."""
        task = _make_task()
        original = TaskExecutor._task_metadata
        TaskExecutor._task_metadata = staticmethod(
            lambda t: (_ for _ in ()).throw(RuntimeError("simulated"))
        )
        try:
            node = executor._convert_task_to_node(task, {})
            assert node is None
        finally:
            TaskExecutor._task_metadata = staticmethod(original)


# ---------------------------------------------------------------------------
# _create_execution_callback / _create_success_criteria
# ---------------------------------------------------------------------------

class TestCreateExecutionCallback:
    def test_explicit_callback(self, executor):
        def cb(**kwargs):
            return {"success": True, "result": "callback_works"}
        task = _make_task(metadata={"execute_callback": cb})
        callback = executor._create_execution_callback(task)
        result = callback(current_state={})
        assert result["success"] is True
        assert result["result"] == "callback_works"
        assert result["execution_attempted"] is True

    def test_explicit_callback_normalizes_dict_result(self, executor):
        def cb(**kwargs):
            return True
        task = _make_task(metadata={"execute_callback": cb})
        callback = executor._create_execution_callback(task)
        result = callback(current_state={})
        assert result["success"] is True
        assert result["execution_attempted"] is True

    def test_no_explicit_callback_returns_real_handler(self, executor):
        task = _make_task()
        callback = executor._create_execution_callback(task)
        assert callable(callback)
        assert callback.__name__ == "callback"


class TestCreateSuccessCriteria:
    def test_custom_checker(self, executor):
        def checker(result, **kwargs):
            return result.get("custom_ok", False)
        task = _make_task(metadata={"success_checker": checker})
        criteria = executor._create_success_criteria(task)
        assert criteria({"custom_ok": True}) is True
        assert criteria({"custom_ok": False}) is False

    def test_custom_checker_exception(self, executor):
        def checker(result, **kwargs):
            raise RuntimeError("boom")
        task = _make_task(metadata={"success_checker": checker})
        criteria = executor._create_success_criteria(task)
        assert criteria({"success": True}) is False

    def test_default_criteria_success(self, executor):
        task = _make_task()
        criteria = executor._create_success_criteria(task)
        assert criteria({"success": True}) is True

    def test_default_criteria_failure(self, executor):
        task = _make_task()
        criteria = executor._create_success_criteria(task)
        assert criteria({"success": False}) is False

    def test_default_criteria_navigate_success(self, executor):
        task = _make_task(task_id="navigate_to_target", metadata={"target_url": "https://example.com"})
        criteria = executor._create_success_criteria(task)
        # Even if normalized success is False, URL matching makes it succeed
        assert criteria({"success": False}, current_url="https://example.com") is True

    def test_default_criteria_navigate_url_mismatch(self, executor):
        task = _make_task(task_id="navigate_to_target", metadata={"target_url": "https://example.com"})
        criteria = executor._create_success_criteria(task)
        assert criteria({"success": False}, current_url="https://different.com") is False

    def test_default_criteria_url_no_target(self, executor):
        task = _make_task(task_id="navigate_to_target")
        criteria = executor._create_success_criteria(task)
        assert criteria({"success": False}) is False

    def test_default_criteria_url_field(self, executor):
        task = _make_task(task_id="navigate_to_target", metadata={"url": "https://example.com"})
        criteria = executor._create_success_criteria(task)
        assert criteria({"success": False}, current_url="https://example.com") is True


# ---------------------------------------------------------------------------
# _apply_result_to_state
# ---------------------------------------------------------------------------

class TestApplyResultToState:
    def test_state_updates_applied(self, executor):
        task = _make_task(task_id="t1", metadata={"action": "test_action", "cost": 1.0})
        executor.execution_context = {"task_id": "t1"}
        result = {"success": True, "state_updates": {"browser_ready": True, "current_url": "https://example.com"}}
        new_state = executor._apply_result_to_state({}, result)
        assert new_state["browser_ready"] is True
        assert new_state["current_url"] == "https://example.com"
        assert "t1" in new_state["completed_tasks"]

    def test_no_state_updates(self, executor):
        executor.execution_context = {"task_id": "t2"}
        result = {"success": True}
        new_state = executor._apply_result_to_state({"existing": True}, result)
        assert new_state["existing"] is True
        assert "t2" in new_state["completed_tasks"]

    def test_result_mappings(self, executor):
        executor.execution_context = {"task_id": "t3"}
        result = {
            "success": True,
            "current_url": "https://test.com",
            "navigator_ready": True,
            "entity_resolved": True,
        }
        new_state = executor._apply_result_to_state({}, result)
        assert new_state["current_url"] == "https://test.com"
        assert new_state["browser_ready"] is True  # navigator_ready -> browser_ready
        assert new_state["entity_resolved"] is True
        assert "t3" in new_state["completed_tasks"]

    def test_unsuccessful_no_completed_task(self, executor):
        executor.execution_context = {"task_id": "t4"}
        result = {"success": False, "state_updates": {"flag": True}}
        new_state = executor._apply_result_to_state({}, result)
        assert new_state["flag"] is True
        assert "t4" not in new_state["completed_tasks"]

    def test_no_execution_context_task_id(self, executor):
        executor.execution_context = {}
        result = {"success": True}
        new_state = executor._apply_result_to_state({}, result)
        assert new_state.get("completed_tasks", []) == []


# ---------------------------------------------------------------------------
# _should_execute_conditionally
# ---------------------------------------------------------------------------

class TestShouldExecuteConditionally:
    def test_no_conditions(self, executor):
        task = _make_task()
        assert executor._should_execute_conditionally(task, {}) is True

    def test_browser_ready_true(self, executor):
        task = _make_task(metadata={"conditions": ["browser_ready"]})
        assert executor._should_execute_conditionally(task, {"browser_ready": True}) is True

    def test_browser_ready_false(self, executor):
        task = _make_task(metadata={"conditions": ["browser_ready"]})
        assert executor._should_execute_conditionally(task, {"browser_ready": False}) is False

    def test_browser_ready_missing(self, executor):
        task = _make_task(metadata={"conditions": ["browser_ready"]})
        assert executor._should_execute_conditionally(task, {}) is False

    def test_entity_resolved_true(self, executor):
        task = _make_task(metadata={"conditions": ["entity_resolved"]})
        assert executor._should_execute_conditionally(task, {"entity_resolved": True}) is True

    def test_entity_resolved_false(self, executor):
        task = _make_task(metadata={"conditions": ["entity_resolved"]})
        assert executor._should_execute_conditionally(task, {"entity_resolved": False}) is False

    def test_custom_string_condition_true(self, executor):
        task = _make_task(metadata={"conditions": ["custom_flag"]})
        assert executor._should_execute_conditionally(task, {"custom_flag": True}) is True

    def test_custom_string_condition_false(self, executor):
        task = _make_task(metadata={"conditions": ["custom_flag"]})
        assert executor._should_execute_conditionally(task, {"custom_flag": False}) is False

    def test_custom_string_condition_missing(self, executor):
        task = _make_task(metadata={"conditions": ["custom_flag"]})
        assert executor._should_execute_conditionally(task, {}) is False

    def test_callable_condition_true(self, executor):
        task = _make_task(metadata={"conditions": [lambda s: s.get("ready")]})
        assert executor._should_execute_conditionally(task, {"ready": True}) is True

    def test_callable_condition_false(self, executor):
        task = _make_task(metadata={"conditions": [lambda s: s.get("ready")]})
        assert executor._should_execute_conditionally(task, {"ready": False}) is False

    def test_callable_condition_exception(self, executor):
        def bad_condition(s):
            raise RuntimeError("boom")
        task = _make_task(metadata={"conditions": [bad_condition]})
        assert executor._should_execute_conditionally(task, {}) is False

    def test_multiple_conditions_all_pass(self, executor):
        task = _make_task(metadata={"conditions": ["browser_ready", "entity_resolved"]})
        assert executor._should_execute_conditionally(task, {"browser_ready": True, "entity_resolved": True}) is True

    def test_multiple_conditions_one_fails(self, executor):
        task = _make_task(metadata={"conditions": ["browser_ready", "entity_resolved"]})
        assert executor._should_execute_conditionally(task, {"browser_ready": False, "entity_resolved": True}) is False

    def test_empty_conditions_list(self, executor):
        task = _make_task(metadata={"conditions": []})
        assert executor._should_execute_conditionally(task, {}) is True


# ---------------------------------------------------------------------------
# execute_task / execute_task_with_retry
# ---------------------------------------------------------------------------

class TestExecuteTask:
    def test_successful_execution(self, executor):
        def cb(**kwargs):
            return {"success": True, "result": "completed"}
        task = _make_task(metadata={"execute_callback": cb, "cost": 1.0})
        result = executor.execute_task(task, {})
        assert result.status == TaskStatus.COMPLETED
        assert result.result["success"] is True

    def test_precondition_failure(self, executor):
        task = _make_task(metadata={"cost": 1.0, "preconditions": ["missing_flag"]})
        result = executor.execute_task(task, {})
        assert result.status == TaskStatus.FAILED
        assert "Precondiciones" in result.error_message

    def test_no_action_no_callback_failure(self, executor):
        task = _make_task()
        result = executor.execute_task(task, {})
        assert result.status == TaskStatus.FAILED

    def test_stats_track_success(self, executor):
        def cb(**kwargs):
            return {"success": True}
        task = _make_task(metadata={"execute_callback": cb})
        before = executor.successful_executions
        executor.execute_task(task, {})
        assert executor.successful_executions == before + 1

    def test_stats_track_failure(self, executor):
        task = _make_task()
        before = executor.failed_executions
        executor.execute_task(task, {})
        assert executor.failed_executions == before + 1

    def test_status_idle_after_execution(self, executor):
        def cb(**kwargs):
            return {"success": True}
        task = _make_task(metadata={"execute_callback": cb})
        executor.execute_task(task, {})
        assert executor.status == TaskExecutorStatus.IDLE
        assert executor.current_task is None

    def test_timeout_exceeded_fails(self, executor):
        def cb(**kwargs):
            return {"success": True}
        task = _make_task(metadata={"execute_callback": cb})
        config = TaskExecutionConfig(timeout_per_task=0.0, max_retries=0)
        te = TaskExecutor(config=config)
        # timeout_per_task=0.0 means timeout check is skipped (0.0 is not > 0)
        result = te.execute_task(task, {})
        assert result.status == TaskStatus.COMPLETED


class TestExecuteTaskWithRetry:
    def test_retry_safe_succeeds_on_retry(self, executor):
        call_count = [0]

        def cb(**kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                return {"success": False, "execution_attempted": True, "error": "fail"}
            return {"success": True}

        task = _make_task(metadata={"execute_callback": cb, "retry_safe": True})
        config = TaskExecutionConfig(max_retries=3, retry_delay=0.0)
        te = TaskExecutor(config=config)
        result = te.execute_task_with_retry(task, {})
        assert result.status == TaskStatus.COMPLETED
        assert call_count[0] == 3

    def test_not_retry_safe_stops_on_first_failure(self, executor):
        task = _make_task()
        config = TaskExecutionConfig(max_retries=5, retry_delay=0.0)
        te = TaskExecutor(config=config)
        result = te.execute_task_with_retry(task, {})
        assert result.status == TaskStatus.FAILED
        assert te.total_attempts == 1

    def test_retry_safe_max_retries_exhausted(self, executor):
        task = _make_task(
            metadata={
                "execute_callback": lambda **kw: {"success": False, "execution_attempted": True},
                "retry_safe": True,
            }
        )
        config = TaskExecutionConfig(max_retries=2, retry_delay=0.0)
        te = TaskExecutor(config=config)
        result = te.execute_task_with_retry(task, {})
        assert result.status == TaskStatus.FAILED
        assert te.total_attempts == 3

    def test_retry_safe_stops_after_execution_attempt(self, executor):
        """When action_attempted is True and retry_safe is False, stops after first attempt."""
        task = _make_task(
            metadata={
                "execute_callback": lambda **kw: {"success": False, "execution_attempted": True},
                "retry_safe": False,
            }
        )
        config = TaskExecutionConfig(max_retries=5, retry_delay=0.0)
        te = TaskExecutor(config=config)
        result = te.execute_task_with_retry(task, {})
        assert result.status == TaskStatus.FAILED
        assert te.total_attempts == 1

    def test_non_retry_safe_allows_retry_on_no_attempt(self, executor):
        """When action_attempted is False, non-retry-safe tasks still retry."""
        call_count = [0]

        def cb(**kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                return {"success": False, "execution_attempted": False}
            return {"success": True}

        task = _make_task(metadata={"execute_callback": cb, "retry_safe": False})
        config = TaskExecutionConfig(max_retries=3, retry_delay=0.0)
        te = TaskExecutor(config=config)
        result = te.execute_task_with_retry(task, {})
        assert result.status == TaskStatus.COMPLETED
        assert te.total_attempts == 2


# ---------------------------------------------------------------------------
# execute_task_hierarchy
# ---------------------------------------------------------------------------

class TestExecuteTaskHierarchy:
    def _make_callback_task(self, name, result_data=None):
        def cb(**kwargs):
            return result_data or {"success": True, "result": f"{name}_done"}
        return _make_task(
            task_id=name,
            name=name,
            metadata={"execute_callback": cb, "cost": 1.0},
        )

    def test_sequential_all_success(self, executor):
        tasks = [
            self._make_callback_task("task_a"),
            self._make_callback_task("task_b"),
        ]
        results = executor.execute_task_hierarchy(tasks, {}, mode=TaskExecutionMode.SEQUENTIAL)
        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_sequential_stops_on_failure(self, executor):
        task_a = self._make_callback_task("task_a")
        task_b = _make_task(task_id="task_b", name="task_b", metadata={"cost": 1.0})
        results = executor.execute_task_hierarchy([task_a, task_b], {}, mode=TaskExecutionMode.SEQUENTIAL)
        assert len(results) == 2
        assert results[0].status == TaskStatus.COMPLETED
        assert results[1].status == TaskStatus.FAILED

    def test_sequential_empty(self, executor):
        results = executor.execute_task_hierarchy([], {}, mode=TaskExecutionMode.SEQUENTIAL)
        assert results == []

    def test_parallel_disabled_falls_back_to_sequential(self, executor):
        tasks = [
            self._make_callback_task("task_a"),
            self._make_callback_task("task_b"),
        ]
        results = executor.execute_task_hierarchy(tasks, {}, mode=TaskExecutionMode.PARALLEL)
        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_parallel_enabled(self, patched_logger):
        config = TaskExecutionConfig(parallel_execution=True)
        te = TaskExecutor(config=config)
        tasks = [
            self._make_callback_task("task_a"),
            self._make_callback_task("task_b"),
        ]
        results = te.execute_task_hierarchy(tasks, {}, mode=TaskExecutionMode.PARALLEL)
        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_parallel_with_inter_task_dependency(self, patched_logger):
        """When tasks have dependencies between them, parallel falls back to sequential."""
        config = TaskExecutionConfig(parallel_execution=True)
        te = TaskExecutor(config=config)
        task_a = self._make_callback_task("task_a")
        task_b = _make_task(task_id="task_b", name="task_b", metadata={"cost": 1.0})
        task_a.dependencies = ["task_b"]
        results = te.execute_task_hierarchy([task_a, task_b], {}, mode=TaskExecutionMode.PARALLEL)
        # Falls back to sequential; task_a depends on task_b but task_b hasn't completed first,
        # so task_a fails and the sequence stops.
        assert len(results) == 1
        assert results[0].status == TaskStatus.FAILED

    def test_conditional_skips_when_condition_false(self, executor):
        task = _make_task(
            task_id="conditional_task",
            name="cond_task",
            metadata={"conditions": ["browser_ready"], "cost": 1.0},
        )
        results = executor.execute_task_hierarchy([task], {}, mode=TaskExecutionMode.CONDITIONAL)
        assert len(results) == 1
        assert results[0].status == TaskStatus.ABORTED

    def test_conditional_executes_when_condition_true(self, executor):
        def cb(**kwargs):
            return {"success": True}
        task = _make_task(
            task_id="conditional_task",
            name="cond_task",
            metadata={"conditions": ["browser_ready"], "execute_callback": cb},
        )
        results = executor.execute_task_hierarchy([task], {"browser_ready": True}, mode=TaskExecutionMode.CONDITIONAL)
        assert len(results) == 1
        assert results[0].status == TaskStatus.COMPLETED

    def test_fallback_mode(self, executor):
        def cb(**kwargs):
            return {"success": True}
        task = _make_task(
            task_id="fallback_task",
            name="fb_task",
            metadata={"execute_callback": cb, "retry_safe": True},
        )
        results = executor.execute_task_hierarchy([task], {}, mode=TaskExecutionMode.FALLBACK)
        assert len(results) == 1
        assert results[0].status == TaskStatus.COMPLETED

    def test_invalid_mode_value_error(self, executor):
        """execute_task_hierarchy raises ValueError for unsupported modes."""
        mock_mode = SimpleNamespace(value="unsupported")
        with pytest.raises(ValueError, match="no soportado"):
            executor.execute_task_hierarchy([], {}, mode=mock_mode)


# ---------------------------------------------------------------------------
# _execute_node (TaskExecutor's own)
# ---------------------------------------------------------------------------

class TestExecuteNode:
    def test_no_callback(self, executor, patched_logger):
        from src.hands.planner.node import Node
        node = Node(id="test", type=NodeType.ACTION, name="test")
        result = executor._execute_node(node, {})
        assert result["success"] is False
        assert result["execution_attempted"] is False

    def test_callback_success(self, executor, patched_logger):
        from src.hands.planner.node import Node

        def cb(**kwargs):
            return {"success": True, "result": "ok"}
        node = Node(id="test", type=NodeType.ACTION, name="test")
        node.execute_callback = cb
        node.parameters = {}
        node.state_modifications = {}
        node.success_criteria = None
        result = executor._execute_node(node, {})
        assert result["success"] is True

    def test_callback_failure(self, executor, patched_logger):
        from src.hands.planner.node import Node

        def cb(**kwargs):
            return {"success": False, "error": "failed"}
        node = Node(id="test", type=NodeType.ACTION, name="test")
        node.execute_callback = cb
        node.parameters = {}
        node.state_modifications = {}
        node.success_criteria = None
        result = executor._execute_node(node, {})
        assert result["success"] is False

    def test_callback_exception(self, patched_logger, executor):
        from src.hands.planner.node import Node

        def cb(**kwargs):
            raise RuntimeError("callback boom")
        node = Node(id="test", type=NodeType.ACTION, name="test")
        node.execute_callback = cb
        node.parameters = {}
        node.state_modifications = {}
        node.success_criteria = None
        result = executor._execute_node(node, {})
        assert result["success"] is False
        assert "callback boom" in result["error"]

    def test_success_criteria_prevents_success(self, executor, patched_logger):
        from src.hands.planner.node import Node

        def cb(**kwargs):
            return {"success": True, "result": "ok"}

        def criteria(result, **kwargs):
            return False
        node = Node(id="test", type=NodeType.ACTION, name="test")
        node.execute_callback = cb
        node.parameters = {}
        node.state_modifications = {}
        node.success_criteria = criteria
        result = executor._execute_node(node, {})
        assert result["success"] is False
        assert "criterio" in result["error"].lower()


# ---------------------------------------------------------------------------
# get_execution_statistics / _update_execution_statistics
# ---------------------------------------------------------------------------

class TestExecutionStatistics:
    def test_initial_statistics(self, executor):
        stats = executor.get_execution_statistics()
        assert stats["status"] == "idle"
        assert stats["total_executions"] == 0
        assert stats["total_attempts"] == 0
        assert stats["successful_executions"] == 0
        assert stats["failed_executions"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["average_execution_time"] == 0.0
        assert stats["current_task"] is None

    def test_stats_after_success(self, executor):
        def cb(**kwargs):
            return {"success": True}
        task = _make_task(metadata={"execute_callback": cb})
        executor.execute_task(task, {})
        stats = executor.get_execution_statistics()
        assert stats["total_executions"] == 1
        assert stats["successful_executions"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["status"] == "idle"  # status resets to IDLE in finally block

    def test_stats_after_failure(self, executor):
        task = _make_task()
        executor.execute_task(task, {})
        stats = executor.get_execution_statistics()
        assert stats["total_executions"] == 1
        assert stats["failed_executions"] == 1
        assert stats["success_rate"] == 0.0
        assert stats["status"] == "idle"

    def test_update_execution_statistics_single(self, executor):
        executor.total_executions = 1
        executor._update_execution_statistics(2.5)
        assert executor.average_execution_time == 2.5

    def test_update_execution_statistics_multiple(self, executor):
        executor.total_executions = 1
        executor._update_execution_statistics(2.0)
        executor.total_executions = 2
        executor._update_execution_statistics(4.0)
        # formula: ((avg * (count-1)) + elapsed) / count = ((2.0 * 1) + 4.0) / 2 = 3.0
        assert executor.average_execution_time == 3.0

    def test_update_execution_statistics_zero_count(self, executor):
        executor.total_executions = 0
        executor._update_execution_statistics(5.0)
        assert executor.average_execution_time == 5.0

    def test_update_execution_statistics_negative(self, executor):
        executor.total_executions = 1
        executor._update_execution_statistics(-1.0)
        assert executor.average_execution_time == 0.0

    def test_update_execution_statistics_thread_safety(self, executor):
        """_update_execution_statistics uses a lock for thread safety."""
        assert hasattr(executor, "_stats_lock")


# ---------------------------------------------------------------------------
# Legacy capability handlers
# ---------------------------------------------------------------------------

class TestLegacyCapabilityHandlers:
    def test_execute_prepare_navigator(self, executor):
        result = executor._execute_prepare_navigator(current_state={})
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_navigate_to_target(self, executor):
        result = executor._execute_navigate_to_target(current_state={})
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_check_availability(self, executor):
        result = executor._execute_check_availability(current_state={})
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_open_application(self, executor):
        result = executor._execute_open_application(current_state={})
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_activate_window(self, executor):
        result = executor._execute_activate_window(current_state={})
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_navigate_to_search_engine(self, executor):
        result = executor._execute_navigate_to_search_engine(current_state={})
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_perform_search(self, executor):
        result = executor._execute_perform_search(current_state={})
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_legacy_task_capability(self, executor):
        result = executor._execute_legacy_task_capability("prepare_navigator", {"current_state": {}})
        assert isinstance(result, dict)
        assert "success" in result


# ---------------------------------------------------------------------------
# execute_task_hierarchy modes: empty input
# ---------------------------------------------------------------------------

class TestExecuteHierarchyEmpty:
    def test_sequential_empty(self, executor):
        assert executor.execute_task_hierarchy([], {}, mode=TaskExecutionMode.SEQUENTIAL) == []

    def test_parallel_empty(self, executor):
        assert executor.execute_task_hierarchy([], {}, mode=TaskExecutionMode.PARALLEL) == []

    def test_conditional_empty(self, executor):
        assert executor.execute_task_hierarchy([], {}, mode=TaskExecutionMode.CONDITIONAL) == []

    def test_fallback_empty(self, executor):
        assert executor.execute_task_hierarchy([], {}, mode=TaskExecutionMode.FALLBACK) == []


# ---------------------------------------------------------------------------
# get_task_executor singleton
# ---------------------------------------------------------------------------

class TestGetTaskExecutor:
    def test_returns_task_executor(self):
        import src.hands.planner.task_executor as mod
        original = mod._task_executor
        mod._task_executor = None
        try:
            te = get_task_executor()
            assert isinstance(te, TaskExecutor)
            te2 = get_task_executor()
            assert te is te2
        finally:
            mod._task_executor = original

    def test_singleton_thread_safety(self):
        """get_task_executor uses a lock for thread safety."""
        import src.hands.planner.task_executor as mod
        assert hasattr(mod, "_task_executor_lock")
        assert isinstance(mod._task_executor_lock, type(threading.RLock()))
