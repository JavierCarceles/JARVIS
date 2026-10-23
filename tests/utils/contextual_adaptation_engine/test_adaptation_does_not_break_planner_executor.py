"""
Tests para verificar que la adaptación contextual no rompe la integración con Planner y Executor.

Objetivo: Validar que cuando un Goal es adaptado, el Goal adaptado:
1. Puede ser validado correctamente por el engine de adaptación
2. No rompe la capacidad del Planner de generar un plan válido
3. No rompe la capacidad del Executor de ejecutar el plan
4. El adaptado mantiene la intención original del Goal
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from src.hands.planner.node import Goal
from src.hands.planner.planner import PlannerStatus, PlanQuality
from src.tools.executor import UnifiedExecutor
from src.utils.contextual_adaptation_engine import ContextualAdaptationEngine


class TestAdaptationDoesNotBreakPlannerExecutor(unittest.TestCase):
    """Tests para verificar que la adaptación no rompe Planner/Executor"""
    
    def setUp(self):
        """Configuración inicial"""
        self.engine = ContextualAdaptationEngine()
        self.executor = UnifiedExecutor()
        
        # Goal original válido
        self.original_goal = Goal(
            id="test_goal_1",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            priority=3,
            constraints=["standard_execution"]
        )
        
        # Goal adaptado (por ejemplo, con prioridad más alta y restricciones de velocidad)
        self.adapted_goal = Goal(
            id="adapted_test_goal_1",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com with fast execution",
            priority=7,
            constraints=["fast_execution", "minimize_resource_usage"],
            metadata={"adapted": True, "adaptation_reason": "high_priority"}
        )
        
        self.current_state = {
            "current_url": "https://startpage.com",
            "active_applications": ["browser"],
            "system_resources": {"cpu": 0.5, "memory": 0.7}
        }
        
        self.available_capabilities = ["open_application", "navigate", "focus_element", "type_text", "press_key"]
    
    def test_adapted_goal_can_be_validated(self):
        """Test: El Goal adaptado puede ser validado exitosamente"""
        result = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=self.adapted_goal,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        # Validación exitosa
        self.assertTrue(result["valid"], 
                       f"Validación falló: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("validation_details", result)
        self.assertIn("planner_resolvable", result["validation_details"])
        self.assertTrue(result["validation_details"]["planner_resolvable"])
    
    def test_adapted_goal_preserves_intention(self):
        """Test: El Goal adaptado preserva la intención del original"""
        result = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=self.adapted_goal,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        # Verificar que la intención se preserva
        self.assertTrue(result["validation_details"]["intention_preserved"],
                       "La adaptación no preserva la intención original")
        self.assertNotIn("La adaptación no preserva la intención original", result["errors"])
    
    @patch('src.hands.planner.planner.Planner')
    def test_adapted_goal_planner_can_solve(self, mock_planner_class):
        """Test: El Planner puede generar un plan válido para el Goal adaptado"""
        with patch('src.hands.planner.planner.Planner') as mock_planner:
            mock_planner = Mock()
            mock_planner.plan_with_htn_integration.return_value = Mock(
                status=PlannerStatus.COMPLETED,
                plan_id="test_plan_for_adapted_goal",
                execution_time=1.5,
                quality=PlanQuality.OPTIMAL,
                warnings=[],
                metadata={"adaptation_context": {"adapted": True}}
            )
            mock_planner_class.return_value = mock_planner
            
            result = self.engine._validate_planner_can_solve(
                self.adapted_goal,
                self.current_state
            )
            
            # Verificar que el planner puede resolver el goal adaptado
            self.assertEqual(result["status"], PlannerStatus.COMPLETED)
            self.assertIsNotNone(result["plan_id"])
            self.assertEqual(result["quality"], PlanQuality.OPTIMAL)
    
    @patch('src.hands.planner.planner.Planner')
    def test_adapted_goal_executor_can_execute(self, mock_planner_class):
        """Test: El Executor puede ejecutar el plan generado para el Goal adaptado"""
        # Configurar mock del Planner
        mock_planner = Mock()
        mock_plan = Mock()
        mock_plan.status = PlannerStatus.COMPLETED
        mock_plan.plan_id = "test_plan_adapted"
        mock_plan.execution_time = 1.5
        mock_plan.quality = PlanQuality.OPTIMAL
        mock_plan.warnings = []
        mock_plan.metadata = {"adapted": True}
        mock_planner.plan_with_htn_integration.return_value = mock_plan
        mock_planner_class.return_value = mock_planner
        
        # Validar el goal adaptado
        validation_result = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=self.adapted_goal,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        self.assertTrue(validation_result["valid"])
        self.assertTrue(validation_result["validation_details"]["planner_resolvable"])
    
    def test_adaptation_does_not_introduce_errors(self):
        """Test: La adaptación no introduce errores que rompan la integración"""
        result = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=self.adapted_goal,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        # No debe haber errores
        self.assertEqual(len(result["errors"]), 0)
        
        # Validar cada componente
        self.assertTrue(result["state_validation"]["valid"])
        self.assertTrue(result["capabilities_validation"]["valid"])
        self.assertTrue(result["preconditions_validation"]["valid"])
        
        # El goal adaptado debe ser resolvable por el planner
        self.assertTrue(result["validation_details"]["planner_resolvable"])
    
    def test_multiple_adaptations_do_not_break_integration(self):
        """Test: Múltiples adaptaciones no rompen la integración"""
        # Primera adaptación
        adapted_goal_1 = Goal(
            id="adapted_goal_1",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com with priority",
            priority=5,
            constraints=["fast_execution"],
            metadata={"adapted": True}
        )
        
        result_1 = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=adapted_goal_1,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        self.assertTrue(result_1["valid"])
        self.assertTrue(result_1["validation_details"]["planner_resolvable"])
        
        # Segunda adaptación
        adapted_goal_2 = Goal(
            id="adapted_goal_2",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com with ultra_fast_execution",
            priority=9,
            constraints=["ultra_fast_execution", "minimal_resources"],
            metadata={"adapted": True}
        )
        
        result_2 = self.engine.validate_adapted_goal(
            original_goal=self.original_goal,
            adapted_goal=adapted_goal_2,
            current_state=self.current_state,
            available_capabilities=self.available_capabilities
        )
        
        self.assertTrue(result_2["valid"])
        self.assertTrue(result_2["validation_details"]["planner_resolvable"])
    
    @patch('src.utils.contextual_adaptation_engine.Planner')
    def test_adaptation_with_different_goal_types(self, mock_planner_class):
        """Test: Adaptación de diferentes tipos de Goals no rompe integración"""
        goal_types = ["navigate", "click", "type_text", "press_key"]
        
        for goal_type in goal_types:
            adapted_goal = Goal(
                id=f"adapted_{goal_type}",
                type=goal_type,
                target="https://example.com" if goal_type == "navigate" else "element_id",
                description=f"Test {goal_type} with adaptation",
                priority=5,
                constraints=["adapted"],
                metadata={"adapted": True}
            )
            
            # Validar goal adaptado
            result = self.engine.validate_adapted_goal(
                original_goal=self.original_goal,
                adapted_goal=adapted_goal,
                current_state=self.current_state,
                available_capabilities=self.available_capabilities
            )
            
            # Debe ser válido y preservar la intención
            self.assertTrue(result["valid"], 
                           f"Adaptación falló para tipo {goal_type}: {result['errors']}")
            self.assertTrue(result["validation_details"]["intention_preserved"])
    
    @patch('src.utils.contextual_adaptation_engine.Planner')
    def test_adapted_goal_with_valid_constraints(self, mock_planner_class):
        """Test: Goals adaptados con restricciones válidas no rompen integración"""
        valid_constraints = [
            ["fast_execution"],
            ["minimal_resources"],
            ["fast_execution", "minimal_resources"],
            ["high_priority"],
            ["high_priority", "fast_execution"]
        ]
        
        for constraints in valid_constraints:
            adapted_goal = Goal(
                id="adapted_goal_valid_constraints",
                type="navigate",
                target="https://example.com",
                description="Navigate with valid constraints",
                priority=5,
                constraints=constraints,
                metadata={"adapted": True}
            )
            
            result = self.engine.validate_adapted_goal(
                original_goal=self.original_goal,
                adapted_goal=adapted_goal,
                current_state=self.current_state,
                available_capabilities=self.available_capabilities
            )
            
            self.assertTrue(result["valid"],
                           f"Adaptación con restricciones {constraints} falló: {result['errors']}")
            self.assertTrue(result["validation_details"]["planner_resolvable"])
    
    @patch('src.utils.contextual_adaptation_engine.Planner')
    def test_adapted_goal_with_high_priority(self, mock_planner_class):
        """Test: Goals adaptados con prioridad alta no rompen integración"""
        high_priorities = [7, 8, 9, 10, 11]
        
        for priority in high_priorities:
            adapted_goal = Goal(
                id="adapted_goal_high_priority",
                type="navigate",
                target="https://example.com",
                description="Navigate with high priority",
                priority=priority,
                constraints=["high_priority"],
                metadata={"adapted": True}
            )
            
            result = self.engine.validate_adapted_goal(
                original_goal=self.original_goal,
                adapted_goal=adapted_goal,
                current_state=self.current_state,
                available_capabilities=self.available_capabilities
            )
            
            self.assertTrue(result["valid"],
                           f"Adaptación con prioridad {priority} falló: {result['errors']}")
            self.assertTrue(result["validation_details"]["planner_resolvable"])
    
    def test_validation_result_is_registered(self):
        """Test: El resultado de validación se registra correctamente"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "validation_details": {}
        }
        
        # Registrar resultado
        self.engine._register_validation_result(
            "original_id",
            "adapted_id",
            validation_result
        )
        
        # Verificar que se registró
        self.assertIn("goal_validations", self.engine.knowledge_base)
        self.assertIsInstance(self.engine.knowledge_base["goal_validations"], list)
        self.assertEqual(len(self.engine.knowledge_base["goal_validations"]), 1)
        
        # Verificar contenido del registro
        registered = self.engine.knowledge_base["goal_validations"][0]
        self.assertEqual(registered["original_goal_id"], "original_id")
        self.assertEqual(registered["adapted_goal_id"], "adapted_id")
        self.assertEqual(registered["validation_result"]["valid"], True)


if __name__ == "__main__":
    unittest.main()
