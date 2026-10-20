"""
Tests para la validación de Goal adaptado (2.8.8.5)

Objetivo: Validar Goal adaptado, State, capabilities, precondiciones y Planner
"""

import unittest
import time
from unittest.mock import Mock, patch

from src.hands.planner.node import Goal
from src.hands.planner.planner import PlannerStatus, PlanQuality
from src.utils.contextual_adaptation_engine import ContextualAdaptationEngine


class TestAdaptedGoalValidation(unittest.TestCase):
    """Tests para validación de Goal adaptado"""
    
    def setUp(self):
        """Configuración inicial"""
        self.engine = ContextualAdaptationEngine()
        self.original_goal = Goal(
            id="test_goal_1",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            priority=3,
            constraints=[]
        )
        
        self.adapted_goal = Goal(
            id="adapted_test_goal_1",
            type="navigate", 
            target="https://example.com",
            description="Navigate to example.com with high priority",
            priority=7,
            constraints=["fast_execution"],
            metadata={"adapted": True}
        )
        
        self.current_state = {
            "current_url": "https://startpage.com",
            "active_applications": ["browser"],
            "system_resources": {"cpu": 0.5, "memory": 0.7}
        }
        
        self.available_capabilities = ["open_application", "navigate", "focus_element", "type_text", "press_key"]
    
    def test_validate_goal_structure_success(self):
        """Test de validación de estructura de Goal exitoso"""
        result = self.engine._validate_goal_structure(self.adapted_goal)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIsInstance(result["warnings"], list)
    
    def test_validate_goal_structure_missing_fields(self):
        """Test de validación de Goal con campos faltantes"""
        invalid_goal = Goal(
            id="",  # ID faltante
            type="",  # Type faltante
            target="https://example.com",
            description="",  # Description faltante
            priority=5
        )
        
        result = self.engine._validate_goal_structure(invalid_goal)
        
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)
    
    def test_validate_current_state_success(self):
        """Test de validación de State exitoso"""
        result = self.engine._validate_current_state(self.current_state)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIsInstance(result["warnings"], list)
    
    def test_validate_current_state_invalid_structure(self):
        """Test de validación de State con estructura inválida"""
        invalid_state = "not_a_dict"
        
        result = self.engine._validate_current_state(invalid_state)
        
        self.assertFalse(result["valid"])
        self.assertIn("State debe ser un diccionario", result["errors"])
    
    def test_validate_capabilities_success(self):
        """Test de validación de capacidades exitoso"""
        result = self.engine._validate_capabilities(
            self.adapted_goal, 
            self.available_capabilities
        )
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("required", result)
        self.assertIn("available", result)
    
    def test_validate_capabilities_missing(self):
        """Test de validación de capacidades con capacidades faltantes"""
        insufficient_capabilities = ["open_application"]  # Falta navigate
        
        result = self.engine._validate_capabilities(
            self.adapted_goal,
            insufficient_capabilities
        )
        
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)
        self.assertIn("Capacidades faltantes", result["errors"][0])
    
    def test_validate_goal_preconditions_navigate_success(self):
        """Test de validación de precondiciones para navigate exitoso"""
        result = self.engine._validate_goal_preconditions(
            self.adapted_goal,
            self.current_state
        )
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        # Debería haber un warning porque no estamos en la URL destino
        self.assertIn("Ya estamos en la URL destino", result["warnings"])
    
    def test_validate_goal_preconditions_navigate_invalid_url(self):
        """Test de validación de precondiciones para navigate con URL inválida"""
        invalid_goal = Goal(
            id="test_goal",
            type="navigate",
            target="not_a_url",
            description="Invalid URL",
            priority=3
        )
        
        result = self.engine._validate_goal_preconditions(
            invalid_goal,
            self.current_state
        )
        
        self.assertFalse(result["valid"])
        self.assertIn("URL de navegación inválida", result["errors"])
    
    def test_validate_planner_can_solve_success(self):
        """Test de validación de Planner exitoso"""
        with patch('src.utils.contextual_adaptation_engine.Planner') as mock_planner_class:
            mock_planner = Mock()
            mock_planner.plan_with_htn_integration.return_value = Mock(
                status=PlannerStatus.COMPLETED,
                plan_id="test_plan",
                execution_time=1.5,
                quality=PlanQuality.OPTIMAL,
                warnings=[],
                metadata={}
            )
            mock_planner_class.return_value = mock_planner
            
            result = self.engine._validate_planner_can_solve(
                self.adapted_goal,
                self.current_state
            )
            
            self.assertEqual(result["status"], PlannerStatus.COMPLETED)
            self.assertIsNotNone(result["plan_id"])
            self.assertEqual(result["execution_time"], 1.5)
    
    def test_validate_planner_can_solve_failure(self):
        """Test de validación de Planner con fallo"""
        with patch('src.utils.contextual_adaptation_engine.Planner') as mock_planner_class:
            mock_planner = Mock()
            mock_planner.plan_with_htn_integration.return_value = Mock(
                status=PlannerStatus.FAILED,
                plan_id=None,
                execution_time=0.5,
                quality=PlanQuality.UNCERTAIN,
                warnings=["Goal no alcanzable"],
                metadata={"error": "Goal no alcanzable"}
            )
            mock_planner_class.return_value = mock_planner
            
            result = self.engine._validate_planner_can_solve(
                self.adapted_goal,
                self.current_state
            )
            
            self.assertEqual(result["status"], PlannerStatus.FAILED)
            self.assertIn("Goal no puede resolver el Goal", result["error"])
    
    def test_validate_adapted_goal_complete_success(self):
        """Test de validación completa de Goal adaptado exitoso"""
        result = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=self.adapted_goal,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        self.assertTrue(result["valid"])
        self.assertIn("validation_details", result)
        self.assertIn("state_validation", result)
        self.assertIn("capabilities_validation", result)
        self.assertIn("preconditions_validation", result)
        self.assertIn("planner_result", result)
        self.assertEqual(len(result["errors"]), 0)
    
    def test_validate_adapted_goal_complete_failure(self):
        """Test de validación completa de Goal adaptado con fallo"""
        # Crear un Goal inválido
        invalid_goal = Goal(
            id="",
            type="",
            target="https://example.com",
            description="",
            priority=15  # Prioridad inválida
        )
        
        result = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=invalid_goal,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)
    
    def test_register_validation_result(self):
        """Test de registro de resultado de validación"""
        validation_result = {
            "valid": True,
            "validation_details": [],
            "errors": [],
            "warnings": []
        }
        
        # No debería lanzar excepción
        self.engine._register_validation_result(
            "original_id",
            "adapted_id", 
            validation_result
        )
        
        # Verificar que se registró
        self.assertIn("goal_validations", self.engine.knowledge_base)
        self.assertIsInstance(self.engine.knowledge_base["goal_validations"], list)
        self.assertEqual(len(self.engine.knowledge_base["goal_validations"]), 1)


if __name__ == "__main__":
    unittest.main()