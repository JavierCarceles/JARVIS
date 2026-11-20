# -*- coding: utf-8 -*-
"""Tests para funciones auxiliares de src/hands/planner/graph.py."""

import math
from datetime import date, datetime
from enum import Enum
from pathlib import Path

import pytest

from src.hands.planner.graph import (
    _copy_state,
    _json_safe,
    _safe_float,
    _type_value,
)


class TestSafeFloat:
    def test_valid_float(self):
        assert _safe_float(3.14) == 3.14

    def test_valid_int(self):
        assert _safe_float(5) == 5.0

    def test_string_number(self):
        assert _safe_float("2.5") == 2.5

    def test_invalid_string_returns_default(self):
        assert _safe_float("not_a_number", 9.0) == 9.0

    def test_none_returns_default(self):
        assert _safe_float(None, 7.0) == 7.0

    def test_nan_returns_default(self):
        assert _safe_float(float("nan"), 1.0) == 1.0

    def test_inf_returns_default(self):
        assert _safe_float(float("inf"), 1.0) == 1.0

    def test_neg_inf_returns_default(self):
        assert _safe_float(float("-inf"), 1.0) == 1.0

    def test_default_is_zero(self):
        assert _safe_float("invalid") == 0.0

    def test_overflow_string(self):
        assert _safe_float("1e999", 2.0) == 2.0


class TestCopyState:
    def test_copies_dict(self):
        original = {"key": "value"}
        copied = _copy_state(original)
        assert copied == {"key": "value"}
        assert copied is not original

    def test_deep_copy_nested(self):
        original = {"outer": {"inner": [1, 2, 3]}}
        copied = _copy_state(original)
        copied["outer"]["inner"].append(4)
        assert original["outer"]["inner"] == [1, 2, 3]
        assert copied["outer"]["inner"] == [1, 2, 3, 4]

    def test_none_returns_empty_dict(self):
        assert _copy_state(None) == {}

    def test_non_dict_returns_empty_dict(self):
        assert _copy_state([1, 2, 3]) == {}
        assert _copy_state("string") == {}

    def test_does_not_mutate_original(self):
        original = {"a": 1}
        _copy_state(original)
        assert original == {"a": 1}

    def test_empty_dict(self):
        result = _copy_state({})
        assert result == {}
        assert isinstance(result, dict)


class TestTypeValue:
    def test_enum_value(self):
        class Color(Enum):
            RED = "red"

        assert _type_value(Color.RED) == "red"

    def test_non_enum_value(self):
        assert _type_value("hello") == "hello"
        assert _type_value(42) == 42
        assert _type_value(None) is None


class TestJsonSafe:
    def test_string(self):
        assert _json_safe("hello") == "hello"

    def test_int(self):
        assert _json_safe(42) == 42

    def test_bool(self):
        assert _json_safe(True) is True

    def test_none(self):
        assert _json_safe(None) is None

    def test_float_finite(self):
        assert _json_safe(3.14) == 3.14

    def test_float_nan(self):
        assert _json_safe(float("nan")) == "nan"

    def test_float_inf(self):
        assert _json_safe(float("inf")) == "inf"

    def test_enum(self):
        class Status(Enum):
            OK = "ok"

        assert _json_safe(Status.OK) == "ok"

    def test_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = _json_safe(dt)
        assert isinstance(result, str)
        assert "2024-01-15" in result

    def test_date(self):
        d = date(2024, 1, 15)
        result = _json_safe(d)
        assert isinstance(result, str)
        assert "2024-01-15" in result

    def test_path(self):
        p = Path("some/relative/path")
        assert _json_safe(p) == str(p)

    def test_dict(self):
        result = _json_safe({"a": 1, "b": [2, 3]})
        assert result == {"a": 1, "b": [2, 3]}

    def test_list(self):
        assert _json_safe([1, 2, 3]) == [1, 2, 3]

    def test_tuple_converted_to_list(self):
        assert _json_safe((1, 2, 3)) == [1, 2, 3]

    def test_set_converted_to_list(self):
        result = _json_safe({1, 2, 3})
        assert sorted(result) == [1, 2, 3]

    def test_circular_reference(self):
        d = {}
        d["self"] = d
        result = _json_safe(d)
        assert result["self"] == "<circular-reference>"

    def test_unserializable_fallback_to_repr(self):
        class Weird:
            pass

        result = _json_safe(Weird())
        assert isinstance(result, str)

    def test_dataclass_with_to_dict(self):
        class Obj:
            def to_dict(self):
                return {"key": "value"}

        assert _json_safe(Obj()) == {"key": "value"}

    def test_frozen_set(self):
        result = _json_safe(frozenset([1, 2, 3]))
        assert sorted(result) == [1, 2, 3]
