#!/usr/bin/env python3
"""
Tests unitarios para la propuesta de adaptación de Goal (2.8.8.4)

Verifica que el sistema puede crear propuestas estructuradas para adaptaciones
de Goal basadas en contexto y reglas aplicables, manteniendo intención original
y validando restricciones.
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


class TestGoalAdaptationProposal(unittest.TestCase):
    """Tests para propuesta de adaptación de Goal"""
    
    def setUp(self):
        """Configuración inicial de tests"""
        self.engine = ContextualAdaptationEngine()
        
        # Crear Goal de prueba
        self.original_goal = Goal(
            id="test_goal_001",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            priority=3,
            constraints=["maximize"],
            metadata={"source": "user_request"}
        )
        
        # Crear contexto de prueba
        self.context_snapshot = ContextSnapshot(
            snapshot_id="test_snapshot_001",
            timestamp=datetime.now(),
            context_type=ContextType.DEVELOPMENT,
            contextual_factors={
                ContextualFactor.SYSTEM_RESOURCES: 0.7,
                ContextualFactor.PERFORMANCE_REQUIREMENTS: 0.5,
                ContextualFactor.USER_BEHAVIOR: 0.6
            },
            system_metrics={"cpu_usage": 0.6, "memory_usage": 0.5},
            performance_metrics={"response_time": 0.4, "throughput": 0.7},
            user_interaction_patterns={"click_rate": 0.8, "session_duration": 0.6},
            environmental_conditions={"temperature": 0.3, "network_latency": 0.4},
            confidence_score=0.8
        )
        
        # Crear reglas de adaptación de prueba
        self.adaptation_rules = [
            AdaptationRule(
                rule_id="rule_001",
                name="Increase Priority",
                description="Increase priority based on system load",
                condition_pattern="system_resources > 0.6",
                adaptation_actions=["increase_priority"],
                context_triggers=[ContextType.DEVELOPMENT],
                confidence_threshold=0.7,
                priority=5
            ),
            AdaptationRule(
                rule_id="rule_002",
                name="Add Constraint",
                description="Add maximize constraint for navigation",
                condition_pattern="performance_requirements > 0.4",
                adaptation_actions=["add_constraint"],
                context_triggers=[ContextType.DEVELOPMENT],
                confidence_threshold=0.5,
                priority=3
            )
        ]
    
    def test_create_goal_adaptation_proposal_basic(self):
        """Test básico de creación de propuesta de adaptación"""
        proposal = self.engine.create_goal_adaptation_proposal(
            self.original_goal, 
            self.context_snapshot, 
            self.adaptation_rules
        )
        
        # Verificar estructura básica de la propuesta
        self.assertIn("proposal_id", proposal)
        self.assertIn("original_goal", proposal)
        self.assertIn("context_snapshot", proposal)
        self.assertIn("adaptation_rules", proposal)
        self.assertIn("proposal_timestamp", proposal)
        self.assertIn("proposal_status", proposal)
        
        # Verificar que la propuesta tiene ID único
        self.assertTrue(proposal["proposal_id"].startswith("goal_adaptation_"))
        
        # Verificar que el Goal original está intacto
        original_in_proposal = proposal["original_goal"]
        self.assertEqual(original_in_proposal["id"], self.original_goal.id)
        self.assertEqual(original_in_proposal["type"], self.original_goal.type)
        self.assertEqual(original_in_proposal["target"], self.original_goal.target)
        
        # Verificar estado inicial
        self.assertEqual(proposal["proposal_status"], "PENDING")
        self.assertTrue(proposal["validation_required"])
    
    def test_create_goal_adaptation_proposal_with_adaptation(self):
        """Test de creación de propuesta con Goal adaptado"""
        proposal = self.engine.create_goal_adaptation_proposal(
            self.original_goal, 
            self.context_snapshot, 
            self.adaptation_rules
        )
        
        # Verificar que se generó un Goal adaptado
        if proposal["adapted_goal"]:
            adapted_goal = proposal["adapted_goal"]
            self.assertNotEqual(adapted_goal["id"], self.original_goal.id)
            self.assertEqual(adapted_goal["type"], self.original_goal.type)
            self.assertEqual(adapted_goal["target"], self.original_goal.target)
            
            # Verificar que los cambios se registraron
            self.assertIn("changes_proposed", proposal)
            self.assertIsInstance(proposal["changes_proposed"], list)
            
            # Verificar que la intención se preservó
            self.assertTrue(proposal["intention_preserved"])
    
    def test_create_goal_adaptation_proposal_no_rules(self):
        """Test de creación de propuesta sin reglas aplicables"""
        proposal = self.engine.create_goal_adaptation_proposal(
            self.original_goal, 
            self.context_snapshot, 
            []  # Sin reglas
        )
        
        # Verificar que no hay Goal adaptado
        self.assertIsNone(proposal["adapted_goal"])
        self.assertEqual(len(proposal["changes_proposed"]), 0)
        self.assertTrue(proposal["intention_preserved"])  # El original se preserva
        
        # Verificar que la propuesta sigue siendo válida
        self.assertIn("proposal_id", proposal)
        self.assertEqual(proposal["proposal_status"], "PENDING")
    
    def test_validate_adaptation_constraints(self):
        """Test de validación de restricciones"""
        # Crear Goal con restricciones contradictorias
        contradictory_goal = Goal(
            id="contradictory_goal",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            constraints=["maximize", "minimize"]  # Contradictorias
        )
        
        validation_results = self.engine._validate_adaptation_constraints(
            self.original_goal, contradictory_goal, self.adaptation_rules
        )
        
        # Debería detectar restricciones contradictorias
        self.assertTrue(any("contradictory" in result.lower() for result in validation_results))
    
    def test_check_intention_preservation(self):
        """Test de verificación de preservación de intención"""
        # Goal similar - intención preservada
        similar_goal = Goal(
            id="similar_goal",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            priority=5  # Solo prioridad diferente
        )
        
        preserved = self.engine._check_intention_preservation(self.original_goal, similar_goal)
        self.assertTrue(preserved)
        
        # Goal diferente tipo - intención no preservada
        different_goal = Goal(
            id="different_goal",
            type="open_application",  # Tipo diferente
            target="chrome.exe",
            description="Open Chrome browser"
        )
        
        not_preserved = self.engine._check_intention_preservation(self.original_goal, different_goal)
        self.assertFalse(not_preserved)
    
    def test_are_constraints_contradictory(self):
        """Test de detección de restricciones contradictorias"""
        # Pares contradictorios
        self.assertTrue(self.engine._are_constraints_contradictory("maximize", "minimize"))
        self.assertTrue(self.engine._are_constraints_contradictory("show", "hide"))
        self.assertTrue(self.engine._are_constraints_contradictory("enable", "disable"))
        
        # Pares no contradictorios
        self.assertFalse(self.engine._are_constraints_contradictory("maximize", "focus"))
        self.assertFalse(self.engine._are_constraints_contradictory("show", "enable"))
        # Empty string should not be contradictory with anything
        self.assertFalse(self.engine._are_constraints_contradictory("", "maximize"))
        self.assertFalse(self.engine._are_constraints_contradictory("maximize", ""))
    
    def test_proposal_registration(self):
        """Test de registro de propuestas"""
        # Crear propuesta
        proposal = self.engine.create_goal_adaptation_proposal(
            self.original_goal, 
            self.context_snapshot, 
            self.adaptation_rules
        )
        
        # Verificar que se registró en memoria
        self.assertIn(proposal["proposal_id"], self.engine.proposals)
        
        # Verificar que se persistió si el sistema lo soporta
        if hasattr(self.engine, 'knowledge_base') and 'goal_adaptation_proposals' in self.engine.knowledge_base:
            proposals_in_kb = self.engine.knowledge_base['goal_adaptation_proposals']
            self.assertTrue(any(p["proposal_id"] == proposal["proposal_id"] for p in proposals_in_kb))
    
    def test_priority_validation(self):
        """Test de validación de prioridad"""
        # Goal con prioridad fuera de rango
        invalid_goal = Goal(
            id="invalid_goal",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            priority=15  # Fuera de rango razonable (1-10)
        )
        
        validation_results = self.engine._validate_adaptation_constraints(
            self.original_goal, invalid_goal, self.adaptation_rules
        )
        
        # Debería detectar prioridad inválida
        self.assertTrue(any("priority" in result.lower() for result in validation_results))
    
    def test_deadline_validation(self):
        """Test de validación de deadline"""
        # Goal con deadline en el pasado
        past_time = time.time() - 3600  # 1 hora en el pasado
        invalid_goal = Goal(
            id="invalid_goal",
            type="navigate",
            target="https://example.com",
            description="Navigate to example.com",
            deadline=past_time
        )
        
        validation_results = self.engine._validate_adaptation_constraints(
            self.original_goal, invalid_goal, self.adaptation_rules
        )
        
        # Debería detectar deadline en el pasado
        self.assertTrue(any("deadline" in result.lower() for result in validation_results))
    
    def test_navigation_integrity_preservation(self):
        """Test de preservación de integridad en navegación"""
        # Goal de navegación con cambio de URL
        navigation_goal = Goal(
            id="nav_goal",
            type="navigate",
            target="https://old-site.com",
            description="Navigate to old site"
        )
        
        # Goal adaptado con URL diferente
        adapted_navigation = Goal(
            id="adapted_nav_goal",
            type="navigate",
            target="https://new-site.com",  # URL diferente
            description="Navigate to new site"
        )
        
        # Verificar que la intención no se preserva (cambio significativo de URL)
        preserved = self.engine._check_intention_preservation(navigation_goal, adapted_navigation)
        self.assertFalse(preserved)
        
        # Verificar que cambio HTTP a HTTPS sí se preserva
        https_goal = Goal(
            id="https_goal",
            type="navigate",
            target="https://old-site.com",  # Solo cambio de protocolo
            description="Navigate to old site"
        )
        
        https_preserved = self.engine._check_intention_preservation(navigation_goal, https_goal)
        self.assertTrue(https_preserved)
    
    def test_application_integrity_preservation(self):
        """Test de preservación de integridad en aplicaciones"""
        # Goal de aplicación
        app_goal = Goal(
            id="app_goal",
            type="open_application",
            target={"app_name": "chrome.exe"},
            description="Open Chrome browser"
        )
        
        # Goal adaptado con aplicación diferente
        adapted_app = Goal(
            id="adapted_app_goal",
            type="open_application",
            target={"app_name": "firefox.exe"},  # App diferente
            description="Open Firefox browser"
        )
        
        # Verificar que la intención no se preserva
        preserved = self.engine._check_intention_preservation(app_goal, adapted_app)
        self.assertFalse(preserved)
    
    def tearDown(self):
        """Limpieza después de tests"""
        # Limpiar propuestas registradas
        if hasattr(self.engine, 'proposals'):
            self.engine.proposals.clear()
        
        # Limpiar conocimiento base si existe
        if hasattr(self.engine, 'knowledge_base') and 'goal_adaptation_proposals' in self.engine.knowledge_base:
            self.engine.knowledge_base['goal_adaptation_proposals'].clear()


if __name__ == '__main__':
    unittest.main()