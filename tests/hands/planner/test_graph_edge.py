# -*- coding: utf-8 -*-
"""Tests para GraphEdge (src/hands/planner/graph.py)."""

import math
from dataclasses import is_dataclass
from unittest.mock import MagicMock

import pytest

from src.hands.planner.graph import GraphEdge
from src.hands.planner.preconditions_effects_types import Condition, ConditionType, Effect


class TestGraphEdgePostInit:
    def test_string_ids_converted(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0)
        assert edge.source_id == "a"
        assert edge.target_id == "b"

    def test_int_ids_converted_to_str(self):
        edge = GraphEdge(source_id=10, target_id=20, cost=1.0)
        assert edge.source_id == "10"
        assert edge.target_id == "20"

    def test_cost_normalized_via_safe_float(self):
        edge = GraphEdge(source_id="a", target_id="b", cost="2.5")
        assert edge.cost == 2.5

    def test_invalid_cost_becomes_inf(self):
        edge = GraphEdge(source_id="a", target_id="b", cost="invalid")
        assert edge.cost == float("inf")

    def test_nan_cost_becomes_inf(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=float("nan"))
        assert edge.cost == float("inf")

    def test_negative_cost_stays_negative(self):
        """_safe_float only normalizes non-finite values; negative stays as-is."""
        edge = GraphEdge(source_id="a", target_id="b", cost=-5.0)
        assert edge.cost == -5.0

    def test_none_cost_uses_default_inf(self):
        """_safe_float(None, float("inf")) returns inf since None is invalid."""
        edge = GraphEdge(source_id="a", target_id="b", cost=None)
        assert edge.cost == float("inf")

    def test_transition_type_default(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0)
        assert edge.transition_type == "normal"

    def test_transition_type_none_becomes_normal(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, transition_type=None)
        assert edge.transition_type == "normal"

    def test_conditions_none_becomes_empty_list(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, conditions=None)
        assert edge.conditions == []

    def test_preconditions_none_becomes_empty_list(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, preconditions=None)
        assert edge.preconditions == []

    def test_effects_none_becomes_empty_list(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, effects=None)
        assert edge.effects == []

    def test_is_dataclass(self):
        assert is_dataclass(GraphEdge)


class TestValuesEqual:
    def test_same_string(self):
        assert GraphEdge._values_equal("active", "active") is True

    def test_different_strings(self):
        assert GraphEdge._values_equal("active", "inactive") is False

    def test_case_insensitive_string(self):
        assert GraphEdge._values_equal("Active", "ACTIVE") is True

    def test_whitespace_stripped(self):
        assert GraphEdge._values_equal(" active ", "active") is True

    def test_true_equals_true(self):
        assert GraphEdge._values_equal(True, True) is True

    def test_true_not_equals_one(self):
        """True and 1 should not be considered equal."""
        assert GraphEdge._values_equal(True, 1) is False

    def test_false_not_equals_zero(self):
        assert GraphEdge._values_equal(False, 0) is False

    def test_false_equals_false(self):
        assert GraphEdge._values_equal(False, False) is True

    def test_bool_vs_string_true(self):
        """bool and str compare via str() representation, case-insensitive."""
        assert GraphEdge._values_equal(True, "true") is True
        assert GraphEdge._values_equal(True, "false") is False

    def test_int_equals_string_int(self):
        assert GraphEdge._values_equal(5, "5") is True

    def test_float_equals_string_float(self):
        assert GraphEdge._values_equal(3.14, "3.14") is True

    def test_near_float_equals_string(self):
        """abs_tol=1e-9 means 1.0 vs '1.0001' are not close enough."""
        assert GraphEdge._values_equal(1.0, "1.0001") is False

    def test_close_float_equals_string(self):
        assert GraphEdge._values_equal(1.0, "1.000000000000001") is True

    def test_non_matching_types(self):
        assert GraphEdge._values_equal([1, 2], {1, 2}) is False

    def test_int_vs_int(self):
        assert GraphEdge._values_equal(42, 42) is True

    def test_int_vs_float(self):
        assert GraphEdge._values_equal(5, 5.0) is True

    def test_string_vs_int(self):
        assert GraphEdge._values_equal("5", 5) is True


class TestEvaluateRawCondition:
    def test_empty_string_returns_false(self):
        assert GraphEdge._evaluate_raw_condition("", {"key": True}) is False

    def test_empty_string_with_whitespace(self):
        assert GraphEdge._evaluate_raw_condition("   ", {}) is False

    def test_string_key_true(self):
        # "key" -> state.get("key", False) -> bool
        assert GraphEdge._evaluate_raw_condition("flag", {"flag": True}) is True
        assert GraphEdge._evaluate_raw_condition("flag", {"flag": False}) is False
        assert GraphEdge._evaluate_raw_condition("flag", {}) is False

    def test_string_not_met(self):
        assert GraphEdge._evaluate_raw_condition("flag_not_met", {"flag": True}) is False
        assert GraphEdge._evaluate_raw_condition("flag_not_met", {"flag": False}) is True
        assert GraphEdge._evaluate_raw_condition("flag_not_met", {}) is True

    def test_string_with_colon(self):
        assert GraphEdge._evaluate_raw_condition("status:active", {"status": "active"}) is True
        assert GraphEdge._evaluate_raw_condition("status:active", {"status": "inactive"}) is False

    def test_string_with_colon_case_insensitive(self):
        assert GraphEdge._evaluate_raw_condition("status:active", {"status": "ACTIVE"}) is True

    def test_string_with_colon_and_whitespace(self):
        cond = "  status :  active  "
        assert GraphEdge._evaluate_raw_condition(cond, {"status": "active"}) is True

    def test_dict_state_equals(self):
        cond = {"type": "state_equals", "key": "color", "value": "red"}
        assert GraphEdge._evaluate_raw_condition(cond, {"color": "red"}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"color": "blue"}) is False

    def test_dict_equals_alias(self):
        cond = {"type": "equals", "key": "x", "value": 1}
        assert GraphEdge._evaluate_raw_condition(cond, {"x": 1}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"x": 2}) is False

    def test_dict_state_exists(self):
        cond = {"type": "state_exists", "key": "data"}
        # state_exists requires the value to be not None
        assert GraphEdge._evaluate_raw_condition(cond, {"data": "value"}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"data": None}) is False
        assert GraphEdge._evaluate_raw_condition(cond, {}) is False

    def test_dict_exists_alias(self):
        cond = {"type": "exists", "key": "data"}
        assert GraphEdge._evaluate_raw_condition(cond, {"data": "value"}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {}) is False

    def test_dict_state_not_exists(self):
        cond = {"type": "state_not_exists", "key": "data"}
        assert GraphEdge._evaluate_raw_condition(cond, {}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"data": None}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"data": "value"}) is False

    def test_dict_state_true(self):
        cond = {"type": "state_true", "key": "ready"}
        assert GraphEdge._evaluate_raw_condition(cond, {"ready": True}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"ready": False}) is False
        assert GraphEdge._evaluate_raw_condition(cond, {}) is False

    def test_dict_true_alias(self):
        cond = {"type": "true", "key": "ready"}
        assert GraphEdge._evaluate_raw_condition(cond, {"ready": True}) is True

    def test_dict_state_false(self):
        cond = {"type": "state_false", "key": "ready"}
        assert GraphEdge._evaluate_raw_condition(cond, {"ready": False}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"ready": True}) is False
        assert GraphEdge._evaluate_raw_condition(cond, {}) is True

    def test_dict_false_alias(self):
        cond = {"type": "false", "key": "ready"}
        assert GraphEdge._evaluate_raw_condition(cond, {"ready": False}) is True

    def test_dict_state_greater_than(self):
        cond = {"type": "state_greater_than", "key": "level", "value": 5}
        assert GraphEdge._evaluate_raw_condition(cond, {"level": 10}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"level": 5}) is False
        assert GraphEdge._evaluate_raw_condition(cond, {"level": 3}) is False

    def test_dict_gt_alias(self):
        cond = {"type": "gt", "key": "level", "value": 5}
        assert GraphEdge._evaluate_raw_condition(cond, {"level": 6}) is True

    def test_dict_state_less_than(self):
        cond = {"type": "state_less_than", "key": "level", "value": 5}
        assert GraphEdge._evaluate_raw_condition(cond, {"level": 3}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"level": 5}) is False

    def test_dict_lt_alias(self):
        cond = {"type": "lt", "key": "level", "value": 5}
        assert GraphEdge._evaluate_raw_condition(cond, {"level": 4}) is True

    def test_dict_composite_and_true(self):
        """Composite conditions need a 'key' field because key validation runs before kind dispatch."""
        cond = {"type": "composite_and", "key": "root", "parameters": {"conditions": [
            {"type": "state_true", "key": "a"},
            {"type": "state_true", "key": "b"},
        ]}}
        assert GraphEdge._evaluate_raw_condition(cond, {"a": True, "b": True}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"a": True, "b": False}) is False

    def test_dict_composite_or(self):
        """Composite conditions need a 'key' field because key validation runs before kind dispatch."""
        cond = {"type": "composite_or", "key": "root", "parameters": {"conditions": [
            {"type": "state_true", "key": "a"},
            {"type": "state_true", "key": "b"},
        ]}}
        assert GraphEdge._evaluate_raw_condition(cond, {"a": False, "b": True}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"a": False, "b": False}) is False

    def test_dict_composite_and_conditions_at_top_level(self):
        """Composite conditions need a 'key' field because key validation runs before kind dispatch."""
        cond = {"type": "and", "key": "root", "conditions": [
            {"type": "state_true", "key": "a"},
            {"type": "state_true", "key": "b"},
        ]}
        assert GraphEdge._evaluate_raw_condition(cond, {"a": True, "b": True}) is True

    def test_dict_composite_without_key_returns_false(self):
        """Without a 'key', key validation returns False before kind dispatch."""
        cond = {"type": "composite_and", "parameters": {"conditions": [
            {"type": "state_true", "key": "a"},
            {"type": "state_true", "key": "b"},
        ]}}
        assert GraphEdge._evaluate_raw_condition(cond, {"a": True, "b": True}) is False

    def test_dict_no_key_returns_false(self):
        cond = {"type": "state_true"}
        assert GraphEdge._evaluate_raw_condition(cond, {"ready": True}) is False

    def test_dict_unknown_kind_returns_false(self):
        cond = {"type": "unknown_kind", "key": "x"}
        assert GraphEdge._evaluate_raw_condition(cond, {"x": True}) is False

    def test_dict_default_type_is_state_true(self):
        cond = {"key": "x"}
        assert GraphEdge._evaluate_raw_condition(cond, {"x": True}) is True
        assert GraphEdge._evaluate_raw_condition(cond, {"x": False}) is False

    def test_object_with_evaluate_method(self):
        mock_cond = MagicMock()
        mock_cond.evaluate.return_value = True
        assert GraphEdge._evaluate_raw_condition(mock_cond, {}) is True
        mock_cond.evaluate.return_value = False
        assert GraphEdge._evaluate_raw_condition(mock_cond, {}) is False

    def test_object_with_evaluate_raises(self):
        mock_cond = MagicMock()
        mock_cond.evaluate.side_effect = RuntimeError("boom")
        assert GraphEdge._evaluate_raw_condition(mock_cond, {}) is False

    def test_callable_condition(self):
        cond_fn = lambda state: state.get("ready", False)
        assert GraphEdge._evaluate_raw_condition(cond_fn, {"ready": True}) is True
        assert GraphEdge._evaluate_raw_condition(cond_fn, {"ready": False}) is False

    def test_callable_raises(self):
        def bad(state):
            raise ValueError("nope")
        assert GraphEdge._evaluate_raw_condition(bad, {}) is False

    def test_non_string_non_dict_non_callable_returns_false(self):
        assert GraphEdge._evaluate_raw_condition(42, {}) is False
        assert GraphEdge._evaluate_raw_condition(None, {}) is False


class TestCanTraverse:
    def test_no_conditions_no_preconditions_traversable(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0)
        assert edge.can_traverse({}) is True

    def test_infinite_cost_not_traversable(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=float("inf"))
        assert edge.can_traverse({}) is False

    def test_negative_cost_not_traversable(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=-10.0)
        assert edge.can_traverse({}) is False

    def test_condition_met(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, conditions=["flag"])
        assert edge.can_traverse({"flag": True}) is True
        assert edge.can_traverse({"flag": False}) is False

    def test_condition_not_met(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, conditions=["flag_not_met"])
        assert edge.can_traverse({"flag": True}) is False

    def test_precondition_met(self):
        cond = Condition(type=ConditionType.STATE_TRUE, key="ready")
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, preconditions=[cond])
        assert edge.can_traverse({"ready": True}) is True
        assert edge.can_traverse({"ready": False}) is False

    def test_multiple_conditions_all_must_pass(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         conditions=["a_flag", "b_flag"])
        assert edge.can_traverse({"a_flag": True, "b_flag": True}) is True
        assert edge.can_traverse({"a_flag": True, "b_flag": False}) is False
        assert edge.can_traverse({"a_flag": False, "b_flag": True}) is False

    def test_does_not_mutate_input_state(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, conditions=["flag"])
        state = {"flag": True}
        edge.can_traverse(state)
        assert state == {"flag": True}

    def test_dict_condition_with_colon(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         conditions=["mode:fast"])
        assert edge.can_traverse({"mode": "fast"}) is True
        assert edge.can_traverse({"mode": "slow"}) is False

    def test_precondition_object_with_evaluate(self):
        cond = Condition(type=ConditionType.STATE_EQUALS, key="color", expected_value="red")
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, preconditions=[cond])
        assert edge.can_traverse({"color": "red"}) is True
        assert edge.can_traverse({"color": "blue"}) is False


class TestApplyEffects:
    def test_no_effects_returns_copy(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0)
        state = {"x": 1}
        result = edge.apply_effects(state)
        assert result == {"x": 1}
        assert result is not state

    def test_state_set_effect(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_set", "key": "opened", "value": True}])
        result = edge.apply_effects({})
        assert result == {"opened": True}

    def test_state_set_effect_with_dict_effect_object(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_set", "key": "count", "value": 42}])
        result = edge.apply_effects({"count": 0})
        assert result == {"count": 42}

    def test_state_increment_effect(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_increment", "key": "count", "value": 5}])
        result = edge.apply_effects({"count": 10})
        assert result == {"count": 15.0}

    def test_state_increment_missing_key(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_increment", "key": "count", "value": 3}])
        result = edge.apply_effects({})
        assert result == {"count": 3.0}

    def test_state_decrement_effect(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_decrement", "key": "count", "value": 2}])
        result = edge.apply_effects({"count": 10})
        assert result == {"count": 8.0}

    def test_state_remove_effect(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_remove", "key": "items", "value": "b"}])
        result = edge.apply_effects({"items": ["a", "b", "c"]})
        assert result == {"items": ["a", "c"]}

    def test_state_remove_non_list_key(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_remove", "key": "items", "value": "x"}])
        result = edge.apply_effects({"items": "not_a_list"})
        assert result == {"items": []}

    def test_state_append_effect(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_append", "key": "items", "value": "d"}])
        result = edge.apply_effects({"items": ["a", "b"]})
        assert result == {"items": ["a", "b", "d"]}

    def test_state_append_to_missing_key(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_append", "key": "items", "value": "first"}])
        result = edge.apply_effects({})
        assert result == {"items": ["first"]}

    def test_effect_object_with_apply_method(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[Effect(type="state_set", key="flag", value=True)])
        result = edge.apply_effects({})
        assert result == {"flag": True}

    def test_effect_object_with_apply_old_api(self):
        """Effect.apply with a TypeError on first call retries with empty dict context."""
        mock_effect = MagicMock()
        mock_effect.apply.side_effect = [TypeError("no second arg"), {"modified": True}]
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, effects=[mock_effect])
        result = edge.apply_effects({"original": True})
        assert result == {"modified": True}

    def test_non_dict_effect_skipped(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0, effects=["not_a_dict"])
        result = edge.apply_effects({"keep": True})
        assert result == {"keep": True}

    def test_effect_without_key_skipped(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_set", "value": True}])
        result = edge.apply_effects({})
        assert result == {}

    def test_composite_effect(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "composite", "parameters": {
                             "effects": [
                                 {"type": "state_set", "key": "a", "value": 1},
                                 {"type": "state_set", "key": "b", "value": 2},
                             ],
                         }}])
        result = edge.apply_effects({})
        assert result == {"a": 1, "b": 2}

    def test_composite_effect_applied_incrementally(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "composite", "parameters": {
                             "effects": [
                                 {"type": "state_increment", "key": "count", "value": 1},
                                 {"type": "state_increment", "key": "count", "value": 1},
                             ],
                         }}])
        result = edge.apply_effects({"count": 0})
        assert result == {"count": 2.0}

    def test_does_not_mutate_input_state(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_set", "key": "new", "value": True}])
        state = {"original": True}
        edge.apply_effects(state)
        assert state == {"original": True}
        assert "new" not in state

    def test_multiple_effects_applied_in_order(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[
                             {"type": "state_set", "key": "step1", "value": True},
                             {"type": "state_set", "key": "step2", "value": True},
                         ])
        result = edge.apply_effects({})
        assert result == {"step1": True, "step2": True}

    def test_effect_with_unsupported_type_skipped(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "unsupported_type", "key": "x", "value": 1}])
        result = edge.apply_effects({"keep": True})
        assert result == {"keep": True}

    def test_none_state_returns_empty(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0,
                         effects=[{"type": "state_set", "key": "x", "value": 1}])
        result = edge.apply_effects(None)
        assert result == {"x": 1}

    def test_none_state_no_effects_returns_empty(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=1.0)
        result = edge.apply_effects(None)
        assert result == {}


class TestGetTotalCost:
    def test_basic_cost(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=5.0)
        assert edge.get_total_cost() == 5.0

    def test_cost_plus_effects(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=5.0,
                         effects=[{"type": "state_set", "key": "x", "value": 1}] * 3)
        # 5.0 + 3 * 0.1 = 5.3
        assert edge.get_total_cost({}) == 5.3

    def test_cost_plus_preconditions(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=5.0,
                         effects=[{"type": "state_set", "key": "x", "value": 1}] * 2,
                         preconditions=[Condition(type=ConditionType.STATE_TRUE, key="ready")] * 4)
        # 5.0 + 2*0.1 + 4*0.05 = 5.0 + 0.2 + 0.2 = 5.4
        assert edge.get_total_cost({}) == 5.4

    def test_infinite_cost_returns_inf(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=float("inf"))
        assert edge.get_total_cost({}) == float("inf")

    def test_negative_cost_returns_inf(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=-10.0)
        assert edge.get_total_cost({}) == float("inf")

    def test_ignores_current_state(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=3.0)
        assert edge.get_total_cost({"any": "state"}) == 3.0

    def test_no_effects_no_preconditions(self):
        edge = GraphEdge(source_id="a", target_id="b", cost=2.0)
        assert edge.get_total_cost({}) == 2.0
