# -*- coding: utf-8 -*-
"""Tests de requisitos de calibración (Unidad 3.5.4).

Cubre:
- 3.5.4.1 Aplicación sin requisito de calibración.
- 3.5.4.2 Aplicación con requisito de calibración.
- 3.5.4.3 Requisito pendiente (elemento no calibrado) vs resuelto.
- 3.5.4.4 No regresión (imports/contratos básicos).
"""

import time
from types import SimpleNamespace

import pytest

from src.hands.applications_core import ApplicationKnowledge
from src.hands.calibrator import (
    CalibrationElement,
    CalibrationStatus,
    EnhancedCalibrator,
)
from src.hands.planner.planner import Planner


def _make_calibrator_with_element(
    app: str = "chrome",
    element_type: str = "address_bar",
    status: CalibrationStatus = CalibrationStatus.NOT_CALIBRATED,
    last_calibrated=None,
) -> EnhancedCalibrator:
    cal = EnhancedCalibrator()
    el = CalibrationElement(
        id=f"{app}.{element_type}",
        name=element_type,
        application=app,
        element_type=element_type,
        calibration_status=status,
        last_calibrated=last_calibrated,
    )
    cal.elements[el.id] = el
    return cal


# ---------------------------------------------------------------------------
# 3.5.4.1 Aplicación sin requisito
# ---------------------------------------------------------------------------
class TestApplicationWithoutCalibrationRequirement:
    def test_calibrator_returns_no_requirements_when_no_elements(self):
        cal = EnhancedCalibrator()
        goal = SimpleNamespace(type="navigate", target="chrome")
        assert cal.get_calibration_requirements_for_goal(goal) == []

    def test_planner_exposes_no_requirements_without_calibrator(self):
        planner = Planner.__new__(Planner)
        planner.calibrator = None
        goal = SimpleNamespace(type="navigate", target="chrome")
        assert planner.get_calibration_requirements(goal) == []

    def test_application_knowledge_default_policy_empty(self):
        app = ApplicationKnowledge(name="App", type="app")
        assert app.calibration_policy == []


# ---------------------------------------------------------------------------
# 3.5.4.2 Aplicación con requisito
# ---------------------------------------------------------------------------
class TestApplicationWithCalibrationRequirement:
    def test_calibrator_returns_pending_element(self):
        cal = _make_calibrator_with_element(status=CalibrationStatus.NOT_CALIBRATED)
        goal = SimpleNamespace(type="navigate", target="chrome")
        assert cal.get_calibration_requirements_for_goal(goal) == ["chrome.address_bar"]

    def test_planner_exposes_requirement_from_calibrator(self):
        cal = _make_calibrator_with_element(status=CalibrationStatus.NOT_CALIBRATED)
        planner = Planner.__new__(Planner)
        planner.calibrator = cal
        goal = SimpleNamespace(type="navigate", target="chrome")
        assert planner.get_calibration_requirements(goal) == ["chrome.address_bar"]

    def test_application_knowledge_can_declare_policy(self):
        app = ApplicationKnowledge(
            name="Chrome", type="browser", calibration_policy=["address_bar"]
        )
        assert app.calibration_policy == ["address_bar"]


# ---------------------------------------------------------------------------
# 3.5.4.3 Requisito pendiente
# ---------------------------------------------------------------------------
class TestPendingCalibrationRequirement:
    def test_calibrated_element_is_not_a_requirement(self):
        cal = _make_calibrator_with_element(
            status=CalibrationStatus.CALIBRATED, last_calibrated=time.time()
        )
        goal = SimpleNamespace(type="navigate", target="chrome")
        assert cal.get_calibration_requirements_for_goal(goal) == []

    def test_unknown_status_element_is_pending(self):
        cal = _make_calibrator_with_element(status=CalibrationStatus.UNKNOWN)
        goal = SimpleNamespace(type="navigate", target="chrome")
        # UNKNOWN != CALIBRATED => se considera pendiente
        assert cal.get_calibration_requirements_for_goal(goal) == ["chrome.address_bar"]

    def test_different_target_not_included(self):
        cal = _make_calibrator_with_element(app="chrome", status=CalibrationStatus.NOT_CALIBRATED)
        goal = SimpleNamespace(type="navigate", target="firefox")
        assert cal.get_calibration_requirements_for_goal(goal) == []

    def test_different_goal_type_not_included(self):
        cal = _make_calibrator_with_element(status=CalibrationStatus.NOT_CALIBRATED)
        goal = SimpleNamespace(type="open_application", target="chrome")
        # open_application usa app_window/app_icon, no address_bar
        assert cal.get_calibration_requirements_for_goal(goal) == []


# ---------------------------------------------------------------------------
# 3.5.4.4 No regresión
# ---------------------------------------------------------------------------
class TestNoRegressionCalibrationRequirements:
    def test_imports(self):
        from src.hands.calibrator import get_enhanced_calibrator  # noqa: F401
        from src.hands.planner.planner import Planner as P  # noqa: F401

        assert P is not None

    def test_planner_methods_exist(self):
        assert hasattr(Planner, "get_calibration_requirements")
        assert hasattr(Planner, "get_calibration_requirements_for_goal")
        assert hasattr(Planner, "calibration_requirements_for_goal")
        assert hasattr(Planner, "check_ui_readiness")
