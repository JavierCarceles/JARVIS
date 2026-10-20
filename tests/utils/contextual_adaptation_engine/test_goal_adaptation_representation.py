#!/usr/bin/env python3
"""
Tests unitarios para la representación de adaptación de Goal (2.8.8.2)

Verifica que el sistema puede representar objetivos adaptados basados en contexto
y reglas de adaptación aplicables.
"""

import unittest
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

# Importar clases necesarias
from src.hands.planner.node import Goal
from src.utils.contextual_adaptation_engine import (
    ContextualAdaptationEngine,
    ContextSnapshot,
    ContextType,
    AdaptationRule,
    AdaptationResult,
    ContextualFactor
)


class TestGoalAdaptationRepresentation(unittest.TestCase):
    """Tests para representación de adaptación de Goal"""
    
    def setUp(self):
        """Configuración inicial de tests"""
        self.engine = ContextualAdaptationEngine()
        
        # Crear un Goal original de prueba
        self.original_goal = Goal(
            id="test_goal_001",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            priority=3,
            constraints=["no_interrupt_user"],
            metadata={"browser": "chrome"}
        )
        
        # Crear contexto de prueba
        self.context_snapshot = ContextSnapshot(
            snapshot_id="test_snapshot_001",
            timestamp=datetime.now(),
            context_type=ContextType.DEVELOPMENT,
            confidence_score=0.8,
            contextual_factors={
                ContextualFactor.SYSTEM_RESOURCES: 0.6,
                ContextualFactor.PERFORMANCE_REQUIREMENTS: 0.9
            },
            system_metrics={"cpu_usage": 0.7, "memory_usage": 0.5},
            performance_metrics={"response_time": 150.0, "error_rate": 0.02},
            user_interaction_patterns={"click_frequency": 0.3},
            environmental_conditions={"network_conditions": 0.8}
        )
    
    def test_represent_adaptation_no_rules(self):
        """Test: Sin reglas aplicables, no debe haber adaptación"""
        adapted_goal, metadata = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, []
        )
        
        self.assertIsNone(adapted_goal)
        self.assertEqual(metadata["applied_rules"], [])
        self.assertEqual(metadata["changes_made"], [])
    
    def test_represent_adaptation_priority_change(self):
        """Test: Cambio de prioridad basado en regla"""
        rule = AdaptationRule(
            rule_id="priority_rule_001",
            name="Priority Rule",
            description="Increase priority for development context",
            condition_pattern="development_context",
            adaptation_actions=["increase_priority"],
            context_triggers=[ContextType.DEVELOPMENT],
            priority=5,
            confidence_threshold=0.7,
            enabled=True
        )
        
        adapted_goal, metadata = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, [rule]
        )
        
        self.assertIsNotNone(adapted_goal)
        self.assertEqual(adapted_goal.priority, 5)  # Prioridad cambiada
        self.assertEqual(len(metadata["changes_made"]), 1)
        self.assertIn("priority: 3 -> 5", metadata["changes_made"][0])
    
    def test_represent_adaptation_constraints_addition(self):
        """Test: Adición de restricciones"""
        rule = AdaptationRule(
            rule_id="constraint_rule_001",
            name="Constraint Rule",
            description="Add development-specific constraints",
            condition_pattern="development_constraints",
            adaptation_actions=["add_constraints"],
            context_triggers=[ContextType.DEVELOPMENT],
            priority=3,
            confidence_threshold=0.7,
            enabled=True
        )
        # Agregar constraints dinámicamente después de crear la regla
        rule.constraints = ["development_mode", "debug_logging"]
        
        adapted_goal, metadata = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, [rule]
        )
        
        self.assertIsNotNone(adapted_goal)
        self.assertIn("development_mode", adapted_goal.constraints)
        self.assertIn("debug_logging", adapted_goal.constraints)
        self.assertEqual(len(metadata["changes_made"]), 1)
        self.assertIn("constraints_added: 2", metadata["changes_made"][0])
    
    def test_represent_adaptation_metadata_update(self):
        """Test: Actualización de metadata"""
        rule = AdaptationRule(
            rule_id="metadata_rule_001",
            name="Metadata Rule",
            description="Add development metadata",
            condition_pattern="development_metadata",
            adaptation_actions=["add_metadata"],
            context_triggers=[ContextType.DEVELOPMENT],
            priority=2,
            confidence_threshold=0.7,
            enabled=True
        )
        # Agregar metadata dinámicamente después de crear la regla
        rule.metadata = {"development_mode": True, "auto_save": True}
        
        adapted_goal, metadata = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, [rule]
        )
        
        self.assertIsNotNone(adapted_goal)
        self.assertTrue(adapted_goal.metadata["development_mode"])
        self.assertTrue(adapted_goal.metadata["auto_save"])
        self.assertEqual(len(metadata["changes_made"]), 2)
        self.assertIn("metadata_updated", metadata["changes_made"][1])
    
    def test_represent_adaptation_deadline_addition(self):
        """Test: Añadir deadline"""
        future_time = time.time() + 3600  # 1 hora en el futuro
        rule = AdaptationRule(
            rule_id="deadline_rule_001",
            name="Deadline Rule",
            description="Add deadline for development tasks",
            condition_pattern="development_deadline",
            adaptation_actions=["add_deadline"],
            context_triggers=[ContextType.DEVELOPMENT],
            priority=4,
            confidence_threshold=0.7,
            enabled=True
        )
        # Agregar deadline dinámicamente después de crear la regla
        rule.deadline = future_time
        
        adapted_goal, metadata = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, [rule]
        )
        
        self.assertIsNotNone(adapted_goal)
        self.assertEqual(adapted_goal.deadline, future_time)
        self.assertEqual(len(metadata["changes_made"]), 2)
        self.assertIn("deadline_added", metadata["changes_made"][1])
    
    def test_represent_adaptation_multiple_rules(self):
        """Test: Aplicación de múltiples reglas"""
        rules = [
            AdaptationRule(
                rule_id="priority_rule",
                name="Priority Rule",
                description="Increase priority",
                condition_pattern="priority_increase",
                adaptation_actions=["increase_priority"],
                context_triggers=[ContextType.DEVELOPMENT],
                priority=4,
                confidence_threshold=0.7,
                enabled=True
            ),
            AdaptationRule(
                rule_id="constraint_rule",
                name="Constraint Rule",
                description="Add constraints",
                condition_pattern="add_constraints",
                adaptation_actions=["add_constraints"],
                context_triggers=[ContextType.DEVELOPMENT],
                priority=3,
                confidence_threshold=0.7,
                enabled=True
            ),
            AdaptationRule(
                rule_id="metadata_rule",
                name="Metadata Rule",
                description="Add metadata",
                condition_pattern="add_metadata",
                adaptation_actions=["add_metadata"],
                context_triggers=[ContextType.DEVELOPMENT],
                priority=2,
                confidence_threshold=0.7,
                enabled=True
            )
        ]
        # Agregar atributos dinámicamente
        rules[1].constraints = ["development_mode"]
        rules[2].metadata = {"debug_mode": True}
        
        adapted_goal, metadata = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, rules
        )
        
        self.assertIsNotNone(adapted_goal)
        # La prioridad se toma de la última regla procesada, no de la primera
        self.assertEqual(adapted_goal.priority, 2)  # De la tercera regla
        self.assertIn("development_mode", adapted_goal.constraints)
        self.assertTrue(adapted_goal.metadata["debug_mode"])
        self.assertEqual(len(metadata["changes_made"]), 4)
    
    def test_represent_adaptation_preserve_original(self):
        """Test: El Goal original no debe modificarse"""
        rule = AdaptationRule(
            rule_id="test_rule",
            name="Test Rule",
            description="Test adaptation",
            condition_pattern="test_adaptation",
            adaptation_actions=["test"],
            context_triggers=[ContextType.DEVELOPMENT],
            priority=2,
            confidence_threshold=0.7,
            enabled=True
        )
        
        # Guardar estado original
        original_priority = self.original_goal.priority
        original_constraints = self.original_goal.constraints.copy()
        original_metadata = self.original_goal.metadata.copy()
        
        # Ejecutar adaptación
        adapted_goal, _ = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, [rule]
        )
        
        # Verificar que el original no cambió
        self.assertEqual(self.original_goal.priority, original_priority)
        self.assertEqual(self.original_goal.constraints, original_constraints)
        self.assertEqual(self.original_goal.metadata, original_metadata)
    
    def test_represent_adaptation_trazabilidad(self):
        """Test: Trazabilidad de la adaptación"""
        rule = AdaptationRule(
            rule_id="trace_rule",
            name="Trace Rule",
            description="Test traceability",
            condition_pattern="trace_test",
            adaptation_actions=["test_trace"],
            context_triggers=[ContextType.DEVELOPMENT],
            priority=1,
            confidence_threshold=0.7,
            enabled=True
        )
        
        adapted_goal, metadata = self.engine.represent_adaptation(
            self.original_goal, self.context_snapshot, [rule]
        )
        
        self.assertIsNotNone(adapted_goal)
        self.assertEqual(metadata["original_goal_id"], self.original_goal.id)
        self.assertEqual(metadata["original_goal_type"], self.original_goal.type)
        self.assertEqual(metadata["original_target"], self.original_goal.target)
        self.assertEqual(metadata["adaptation_trigger"], ContextType.DEVELOPMENT.value)
        self.assertEqual(metadata["applied_rules"], [rule.rule_id])
        self.assertIsNotNone(metadata["timestamp"])
        self.assertIsNotNone(metadata["adapted_goal_id"])
        self.assertNotEqual(metadata["adapted_goal_id"], self.original_goal.id)


if __name__ == "__main__":
    unittest.main()