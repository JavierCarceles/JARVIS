# -*- coding: utf-8 -*-
"""Tests de ActionRegistry (src/hands/action_registry.py)."""

from dataclasses import is_dataclass
from unittest.mock import MagicMock

import pytest

from src.hands.action_registry import (
    ActionInfo,
    ActionRegistry,
    ActionType,
    get_action_registry,
)


class TestActionType:
    def test_values(self):
        assert ActionType.APPLICATION.value == "application"
        assert ActionType.SYSTEM.value == "system"
        assert ActionType.NAVIGATION.value == "navigation"
        assert ActionType.INTERACTION.value == "interaction"
        assert ActionType.CALIBRATION.value == "calibration"

    def test_all_distinct(self):
        values = [at.value for at in ActionType]
        assert len(values) == len(set(values))


class TestActionInfo:
    def _make(self, **overrides):
        defaults = dict(
            name="test.action",
            description="A test action",
            action_type=ActionType.APPLICATION,
            function=lambda: None,
            parameters={"arg1": {"type": "str", "default": None, "required": True}},
            module="test_module",
            category="general",
            tags=["tag1"],
            confidence_threshold=0.8,
        )
        defaults.update(overrides)
        return ActionInfo(**defaults)

    def test_post_init_normalizes_fields(self):
        info = self._make(tags=None, dependencies=None, required_resources=None)
        assert info.tags == []
        assert info.dependencies == []
        assert info.required_resources == []

    def test_post_init_resolves_string_action_type(self):
        info = self._make(action_type="system")
        assert info.action_type == ActionType.SYSTEM

    def test_post_init_normalizes_confidence(self):
        info = self._make(confidence_threshold=1.5)
        assert info.confidence_threshold == 1.0

    def test_post_init_normalizes_cost(self):
        info = self._make(cost="5")
        assert info.cost == 5.0

    def test_post_init_invalid_cost_raises(self):
        with pytest.raises(ValueError):
            self._make(cost=-1)

    def test_to_dict_serializes(self):
        info = self._make()
        d = info.to_dict()
        assert d["action"] == "test.action"
        assert d["type"] == "application"
        assert d["category"] == "general"
        assert d["confidence_threshold"] == 0.8
        assert d["planner_enabled"] is True

    def test_to_dict_serializes_functions_as_string(self):
        info = self._make()
        d = info.to_dict()
        assert d["preconditions_functions"] == "FUNCIONES_NO_SERIALIZABLES"
        assert d["effects_functions"] == "FUNCIONES_NO_SERIALIZABLES"

    def test_matches_preconditions_no_conditions(self):
        info = self._make(preconditions=None)
        assert info.matches_preconditions({}) is True

    def test_matches_preconditions_dict_conditions(self):
        info = self._make(preconditions={"ready": True})
        assert info.matches_preconditions({"ready": True}) is True
        assert info.matches_preconditions({"ready": False}) is False

    def test_matches_preconditions_function(self):
        info = self._make(preconditions_functions=[lambda s: s.get("x", 0) > 0])
        assert info.matches_preconditions({"x": 5}) is True
        assert info.matches_preconditions({"x": 0}) is False

    def test_verify_success_no_checker(self):
        info = self._make(success_checker=None)
        assert info.verify_success(None) is True

    def test_verify_success_checker_returns_true(self):
        checker = MagicMock(return_value=True)
        info = self._make(success_checker=checker)
        assert info.verify_success({"ok": True}) is True

    def test_verify_success_checker_returns_false(self):
        checker = MagicMock(return_value=False)
        info = self._make(success_checker=checker)
        assert info.verify_success(None) is False

    def test_apply_effects_empty(self):
        info = self._make(effects=None)
        result = info.apply_effects({"key": "val"}, {})
        assert result == {"key": "val"}

    def test_apply_effects_dict_effect(self):
        info = self._make(effects=[{"key": "new_val", "value": 42, "type": "state_set"}])
        result = info.apply_effects({"key": "old"}, {})
        assert result["new_val"] == 42

    def test_apply_effects_function_effect(self):
        def my_effect(state, exec_result=None):
            state["changed"] = True
            return state
        info = self._make(effects=[my_effect])
        result = info.apply_effects({}, {})
        assert result["changed"] is True


class TestActionRegistryInit:
    def test_default_init(self):
        reg = ActionRegistry()
        assert reg.actions == {}
        assert reg.categories == {}
        assert reg._action_count == 0
        assert reg._execution_count == 0
        assert reg._success_count == 0
        assert reg._error_count == 0

    def test_get_action_registry_singleton(self):
        r1 = get_action_registry()
        r2 = get_action_registry()
        assert r1 is r2


class TestActionRegistryRegister:
    def setup_method(self, _method=None):
        self.reg = ActionRegistry()

    def test_register_action_returns_decorator(self):
        decorator = self.reg.register_action(
            name="test.action", description="desc"
        )
        assert callable(decorator)

    def test_register_action_registers_function(self):
        reg = ActionRegistry()

        @reg.register_action(name="my.action", description="d", category="test")
        def my_action():
            return "result"

        assert "my.action" in reg.actions
        info = reg.get_action("my.action")
        assert info is not None
        assert info.name == "my.action"
        assert info.category == "test"
        assert info.function is my_action

    def test_register_action_empty_name_raises(self):
        with pytest.raises(ValueError, match="no vac"):
            self.reg.register_action(name="", description="d")

    def test_register_action_empty_name_whitespace_raises(self):
        with pytest.raises(ValueError):
            self.reg.register_action(name="   ", description="d")

    def test_register_action_empty_category_raises(self):
        with pytest.raises(ValueError, match="categor"):
            self.reg.register_action(name="x", description="d", category="")

    def test_register_action_invalid_type_raises(self):
        with pytest.raises((ValueError, TypeError)):
            self.reg.register_action(name="x", description="d", action_type="invalid_type")

    def test_register_action_strips_name(self):
        @self.reg.register_action(name="  spaced  ", description="d")
        def f():
            pass

        assert "spaced" in self.reg.actions

    def test_register_action_extracts_parameters_from_func(self):
        @self.reg.register_action(name="param.action", description="d")
        def func_with_params(x: int, y: str = "default"):
            pass

        info = self.reg.get_action("param.action")
        assert "x" in info.parameters
        assert "y" in info.parameters
        assert info.parameters["x"]["required"] is True
        assert info.parameters["y"]["default"] == "default"

    def test_register_action_uses_explicit_parameters(self):
        @self.reg.register_action(
            name="explicit.action", description="d",
            parameters={"x": {"type": "str", "default": "def", "required": False}},
        )
        def f():
            pass

        info = self.reg.get_action("explicit.action")
        assert "x" in info.parameters

    def test_register_action_detects_var_kwargs(self):
        @self.reg.register_action(name="flex", description="d")
        def func(**kwargs):
            pass

        info = self.reg.get_action("flex")
        assert info.allow_extra_parameters is True

    def test_register_action_non_callable_raises(self):
        decorator = self.reg.register_action(name="bad", description="d")
        with pytest.raises(TypeError):
            decorator(42)

    def test_register_action_increments_count(self):
        initial = self.reg._action_count

        @self.reg.register_action(name="a1", description="d")
        def f1():
            pass

        assert self.reg._action_count == initial + 1

    def test_register_action_category_tracking(self):
        @self.reg.register_action(name="cat1.action1", description="d", category="cat_a")
        def f1():
            pass

        @self.reg.register_action(name="cat1.action2", description="d", category="cat_a")
        def f2():
            pass

        @self.reg.register_action(name="cat2.action1", description="d", category="cat_b")
        def f3():
            pass

        assert "cat1.action1" in self.reg.categories["cat_a"]
        assert "cat1.action2" in self.reg.categories["cat_a"]
        assert "cat2.action1" in self.reg.categories["cat_b"]

    def test_register_action_re_register_different_category(self):
        @self.reg.register_action(name="dup", description="d1", category="cat_a")
        def f1():
            pass

        @self.reg.register_action(name="dup", description="d2", category="cat_b")
        def f2():
            pass

        assert "dup" not in self.reg.categories.get("cat_a", [])
        assert "dup" in self.reg.categories.get("cat_b", [])


class TestActionRegistryQuery:
    def setup_method(self, _method=None):
        self.reg = ActionRegistry()

        @self.reg.register_action(name="act1", description="d", category="cat_a")
        def act1():
            pass

        @self.reg.register_action(name="act2", description="d", category="cat_b", planner_enabled=False)
        def act2():
            pass

        @self.reg.register_action(name="act3", description="d", category="cat_a")
        def act3():
            pass

    def test_get_action_found(self):
        info = self.reg.get_action("act1")
        assert info is not None
        assert info.name == "act1"

    def test_get_action_not_found(self):
        assert self.reg.get_action("nonexistent") is None

    def test_get_all_actions(self):
        all_actions = self.reg.get_all_actions()
        assert len(all_actions) == 3
        assert "act1" in all_actions
        assert "act2" in all_actions

    def test_get_actions_by_category(self):
        cat_a = self.reg.get_actions_by_category("cat_a")
        assert len(cat_a) == 2
        cat_b = self.reg.get_actions_by_category("cat_b")
        assert len(cat_b) == 1

    def test_get_actions_by_category_not_found(self):
        result = self.reg.get_actions_by_category("nonexistent")
        assert result == []

    def test_get_plannable_actions(self):
        plannable = self.reg.get_plannable_actions()
        # act2 has planner_enabled=False
        assert "act1" in plannable
        assert "act2" not in plannable
        assert "act3" in plannable

    def test_list_actions_all(self):
        names = self.reg.list_actions()
        assert set(names) == {"act1", "act2", "act3"}

    def test_list_actions_by_category(self):
        cat_a_names = self.reg.list_actions("cat_a")
        assert set(cat_a_names) == {"act1", "act3"}

    def test_list_actions_unknown_category(self):
        assert self.reg.list_actions("unknown") == []

    def test_get_action_categories(self):
        categories = self.reg.get_action_categories()
        assert set(categories) == {"cat_a", "cat_b"}


class TestActionRegistryValidation:
    def setup_method(self, _method=None):
        self.reg = ActionRegistry()

    def test_validate_action_exists_valid_params(self):
        @self.reg.register_action(
            name="valid", description="d",
            parameters={"x": {"type": "str", "default": None, "required": True}},
        )
        def f(x):
            pass

        assert self.reg.validate_action("valid", {"x": "value"}) is True

    def test_validate_action_not_found(self):
        assert self.reg.validate_action("nonexistent", {}) is False

    def test_validate_action_params_not_mapping(self):
        @self.reg.register_action(name="x", description="d")
        def f():
            pass

        assert self.reg.validate_action("x", "not_a_dict") is False

    def test_can_execute_action_exists(self):
        @self.reg.register_action(name="can", description="d")
        def f():
            pass

        assert self.reg.can_execute("can", {}) is True

    def test_can_execute_action_not_found(self):
        assert self.reg.can_execute("nonexistent", {}) is False

    def test_can_execute_with_state_no_preconditions(self):
        @self.reg.register_action(name="nc", description="d")
        def f():
            pass

        assert self.reg.can_execute("nc", {}, state={"ready": True}) is True

    def test_can_execute_with_failing_preconditions(self):
        @self.reg.register_action(
            name="pc", description="d",
            preconditions={"ready": True},
        )
        def f():
            pass

        assert self.reg.can_execute("pc", {}, state={"ready": False}) is False
        assert self.reg.can_execute("pc", {}, state={"ready": True}) is True

    def test_get_action_cost_found(self):
        @self.reg.register_action(name="costly", description="d", cost=5.0)
        def f():
            pass

        assert self.reg.get_action_cost("costly") == 5.0

    def test_get_action_cost_not_found(self):
        with pytest.raises(ValueError, match="no encontrada"):
            self.reg.get_action_cost("nonexistent")


class TestActionRegistryIntegration:
    def test_get_actions_for_planner_returns_dicts(self):
        reg = ActionRegistry()

        @reg.register_action(name="p1", description="d", category="c")
        def f1():
            pass

        actions = reg.get_actions_for_planner()
        assert len(actions) == 1
        assert isinstance(actions[0], dict)
        assert actions[0]["action"] == "p1"

    def test_get_actions_for_planner_excludes_disabled(self):
        reg = ActionRegistry()

        @reg.register_action(name="p1", description="d", planner_enabled=True)
        def f1():
            pass

        @reg.register_action(name="p2", description="d", planner_enabled=False)
        def f2():
            pass

        actions = reg.get_actions_for_planner()
        names = [a["action"] for a in actions]
        assert "p1" in names
        assert "p2" not in names

    def test_get_actions_for_llama_returns_list_of_dicts(self):
        reg = ActionRegistry()

        @reg.register_action(name="ll", description="d")
        def f():
            pass

        actions = reg.get_actions_for_llama()
        assert len(actions) == 1
        assert actions[0]["action"] == "ll"

    def test_get_optimization_stats(self):
        reg = ActionRegistry()

        @reg.register_action(name="a", description="d", category="x")
        def fa():
            pass

        @reg.register_action(name="b", description="d", category="x")
        def fb():
            pass

        stats = reg.get_optimization_stats()
        assert stats["total_actions"] == 2
        assert stats["total_categories"] == 1
        assert "x" in stats["categories"]

    def test_optimize_logging_returns_none(self):
        reg = ActionRegistry()
        result = reg.optimize_logging()
        assert result is None
