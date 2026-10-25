"""
Tests de inicialización para el módulo Brain 2.8.13.5

Verifica que el paquete src.brain exporta correctamente sus componentes
públicos (Brain, HTNBrainIntegration, get_htn_integration) y que
HTNIntegrationResult está disponible como dataclass auxiliar.
"""

import unittest
from dataclasses import is_dataclass, fields

from src.brain import (
    Brain,
    HTNBrainIntegration,
    get_htn_integration,
    __all__,
)
from src.brain.htn_integration import HTNIntegrationResult


class TestBrainInitExports(unittest.TestCase):
    """2.8.13.5.1 — Verificar exports del paquete Brain"""

    def test_2_8_13_5_1_brain_exported(self):
        """Brain debe estar exportado y ser una clase."""
        self.assertTrue(callable(Brain))
        self.assertEqual(Brain.__name__, "Brain")

    def test_2_8_13_5_1_htn_brain_integration_exported(self):
        """HTNBrainIntegration debe estar exportado y ser una clase."""
        self.assertTrue(callable(HTNBrainIntegration))
        self.assertEqual(HTNBrainIntegration.__name__, "HTNBrainIntegration")

    def test_2_8_13_5_1_get_htn_integration_exported(self):
        """get_htn_integration debe estar exportado y ser callable."""
        self.assertTrue(callable(get_htn_integration))

    def test_2_8_13_5_1_htn_integration_result_exported(self):
        """HTNIntegrationResult debe ser un dataclass."""
        self.assertTrue(is_dataclass(HTNIntegrationResult))

    def test_2_8_13_5_1_all_contains_expected_names(self):
        """__all__ debe contener los nombres esperados del paquete Brain."""
        for name in __all__:
            self.assertIn(name, ["Brain", "HTNBrainIntegration", "get_htn_integration"])
        self.assertIn("Brain", __all__)
        self.assertIn("HTNBrainIntegration", __all__)
        self.assertIn("get_htn_integration", __all__)

    def test_2_8_13_5_1_htn_integration_result_fields(self):
        """HTNIntegrationResult debe tener los campos esperados."""
        field_names = {f.name for f in fields(HTNIntegrationResult)}
        expected = {
            "success", "goal_id", "goal_type", "decomposed_tasks",
            "execution_results", "total_execution_time", "message",
            "error_message", "final_state",
        }
        self.assertTrue(expected.issubset(field_names), f"Faltan campos: {expected - field_names}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
