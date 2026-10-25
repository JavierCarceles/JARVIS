# -*- coding: utf-8 -*-
"""Tests de inicialización del paquete hands (src/hands/__init__.py)."""

import unittest


class TestHandsPackageInit(unittest.TestCase):
    def test_executor_exported(self):
        from src.hands import Executor
        self.assertTrue(callable(Executor))

    def test_get_action_registry_exported(self):
        from src.hands import get_action_registry
        self.assertTrue(callable(get_action_registry))

    def test_register_action_exported(self):
        from src.hands import register_action
        self.assertTrue(callable(register_action))

    def test_register_module_exported(self):
        from src.hands import register_module
        self.assertTrue(callable(register_module))

    def test_action_type_exported(self):
        from src.hands import ActionType
        self.assertTrue(hasattr(ActionType, "__members__"))

    def test_get_calibration_manager_exported(self):
        from src.hands import get_calibration_manager
        self.assertTrue(callable(get_calibration_manager))

    def test_calibration_manager_exported(self):
        from src.hands import CalibrationManager
        self.assertTrue(callable(CalibrationManager))

    def test_get_coordinate_manager_exported(self):
        from src.hands import get_coordinate_manager
        self.assertTrue(callable(get_coordinate_manager))

    def test_coordinate_manager_exported(self):
        from src.hands import CoordinateManager
        self.assertTrue(callable(CoordinateManager))

    def test_get_application_manager_exported(self):
        from src.hands import get_application_manager
        self.assertTrue(callable(get_application_manager))

    def test_get_applications_by_capability_exported(self):
        from src.hands import get_applications_by_capability
        self.assertTrue(callable(get_applications_by_capability))

    def test_register_custom_application_exported(self):
        from src.hands import register_custom_application
        self.assertTrue(callable(register_custom_application))

    def test_chrome_submodule_exported(self):
        from src.hands import chrome
        self.assertTrue(hasattr(chrome, "Chrome"))

    def test_keyboard_submodule_exported(self):
        from src.hands import keyboard
        self.assertTrue(hasattr(keyboard, "__name__"))

    def test_mouse_submodule_exported(self):
        from src.hands import mouse
        self.assertTrue(hasattr(mouse, "__name__"))


if __name__ == "__main__":
    unittest.main()
