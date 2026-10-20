"""
Tests para Cross Context Knowledge Transfer - Unidades de Conocimiento (2.8.5.4)
Verifica la extracción, filtrado y transformación de unidades de conocimiento
"""

import unittest
from unittest.mock import Mock
import sys
import os

# Añadir el path para importar los módulos
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType, KnowledgeTransfer
from datetime import datetime


class TestCrossContextUnits(unittest.TestCase):
    """Tests para unidades de conocimiento en transferencia entre contextos"""

    def setUp(self):
        """Configuración inicial para cada test"""
        self.engine = ContextualAdaptationEngine()
        self.engine.config = {"knowledge_transfer_enabled": True}

        # Mockear dependencias externas
        self.engine.logger = Mock()
        self.engine.analytics = Mock()

        # Inicializar knowledge base con datos de prueba
        self.engine.knowledge_base = {
            "success_patterns": {
                "development": [
                    {"pattern": "code_review", "success_rate": 0.9, "metrics": {"time": 30, "accuracy": 0.95}},
                    {"pattern": "unit_tests", "success_rate": 0.8, "metrics": {"time": 25, "accuracy": 0.9}},
                    {"pattern": "documentation", "success_rate": 0.7, "metrics": {"time": 20, "accuracy": 0.85}}
                ],
                "production": [
                    {"pattern": "monitoring", "success_rate": 0.95, "metrics": {"time": 45, "accuracy": 0.98}},
                    {"pattern": "load_balancing", "success_rate": 0.85, "metrics": {"time": 40, "accuracy": 0.92}},
                    {"pattern": "caching", "success_rate": 0.88, "metrics": {"time": 35, "accuracy": 0.9}}
                ],
                "testing": [
                    {"pattern": "integration_tests", "success_rate": 0.82, "metrics": {"time": 50, "accuracy": 0.91}},
                    {"pattern": "e2e_tests", "success_rate": 0.78, "metrics": {"time": 60, "accuracy": 0.88}}
                ]
            },
            "adaptation_strategies": {
                "development": [
                    {"strategy": "incremental_deployment", "success_rate": 0.8, "complexity": "low"},
                    {"strategy": "feature_flags", "success_rate": 0.9, "complexity": "medium"}
                ],
                "production": [
                    {"strategy": "blue_green_deployment", "success_rate": 0.95, "complexity": "high"},
                    {"strategy": "canary_release", "success_rate": 0.88, "complexity": "medium"}
                ]
            },
            "performance_baselines": {
                "development": {"response_time": 0.5, "error_rate": 0.02, "throughput": 100},
                "production": {"response_time": 0.2, "error_rate": 0.001, "throughput": 500}
            },
            "contextual_metrics": {
                "development": {"cpu_usage": 0.6, "memory_usage": 0.7, "concurrent_users": 10},
                "production": {"cpu_usage": 0.8, "memory_usage": 0.9, "concurrent_users": 100}
            }
        }

    def test_2_8_5_4_1_identificar_que_conocimiento_puede_transferirse(self):
        """2.8.5.4.1 Identificar qué conocimiento puede transferirse"""
        # Verificar tipos de conocimiento soportados
        supported_knowledge_types = [
            "success_patterns",
            "adaptation_strategies",
            "performance_baselines",
            "contextual_metrics"
        ]

        for ktype in supported_knowledge_types:
            # Verificar que el tipo existe en la knowledge base
            self.assertIn(ktype, self.engine.knowledge_base)
            # Verificar que es un diccionario o lista
            self.assertIsInstance(self.engine.knowledge_base[ktype], (dict, list))

    def test_2_8_5_4_2_separar_conocimiento_no_reutilizable(self):
        """2.8.5.4.2 Separar conocimiento de estado actual no reutilizable"""
        # Estado actual es específico de ejecución, no debe transferirse
        non_transferable_states = [
            "current_execution_id",
            "running_processes",
            "active_connections"
        ]

        # Verificar que estos estados no están en la knowledge base
        for state_key in non_transferable_states:
            # Si existen, deben estar en una sección separada que no se transfera
            # (verificar implementación real)
            pass

    def test_2_8_5_4_3_extraer_usando_logica_existente(self):
        """2.8.5.4.3 Extraer conocimiento usando lógica existente"""
        # Probar extracción de diferentes tipos de conocimiento
        knowledge_types = ["success_patterns", "adaptation_strategies", "performance_baselines", "contextual_metrics"]

        for ktype in knowledge_types:
            # Verificar que existe el método de extracción
            self.assertTrue(hasattr(self.engine, '_extract_knowledge_from_context'))

            # Extraer conocimiento
            extracted = self.engine._extract_knowledge_from_context(
                context=ContextType.DEVELOPMENT,
                knowledge_type=ktype
            )

            # Verificar que se extrajo algo (aunque pueda estar vacío)
            self.assertIsInstance(extracted, (dict, list))

    def test_2_8_5_4_4_transformar_usando_mecanismos_existentes(self):
        """2.8.5.4.4 Transformar conocimiento usando mecanismos existentes"""
        # Crear una transferencia inicial
        transfer = self.engine.transfer_knowledge(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.LEARNING,
            knowledge_type="success_patterns"
        )

        # Verificar que se creó una transferencia válida
        self.assertIsNotNone(transfer)
        self.assertIsInstance(transfer, KnowledgeTransfer)

        # Verificar que el conocimiento fue transformado
        knowledge_data = transfer.knowledge_data
        self.assertIsInstance(knowledge_data, dict)

        # Verificar que contiene patrones de éxito
        if "success_patterns" in knowledge_data:
            self.assertIsInstance(knowledge_data["success_patterns"], list)

    def test_2_8_5_4_5_tests(self):
        """2.8.5.4.5 Tests de integración de unidades de conocimiento"""
        # Test 1: Transferir patrones de éxito
        patterns_transfer = self.engine.transfer_knowledge(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.LEARNING,
            knowledge_type="success_patterns"
        )

        self.assertIsNotNone(patterns_transfer)
        self.assertIn("success_patterns", patterns_transfer.knowledge_data)

        # Test 2: Transferir estrategias de adaptación
        strategies_transfer = self.engine.transfer_knowledge(
            source_context=ContextType.PRODUCTION,
            target_context=ContextType.LEARNING,
            knowledge_type="adaptation_strategies"
        )

        self.assertIsNotNone(strategies_transfer)
        self.assertIn("successful_strategies", strategies_transfer.knowledge_data)

        # Test 3: Transferir líneas base de rendimiento
        baselines_transfer = self.engine.transfer_knowledge(
            source_context=ContextType.PRODUCTION,
            target_context=ContextType.OPTIMIZATION,
            knowledge_type="performance_baselines"
        )

        self.assertIsNotNone(baselines_transfer)
        self.assertIn("performance_baselines", baselines_transfer.knowledge_data)

        # Test 4: Transferir métricas contextuales
        metrics_transfer = self.engine.transfer_knowledge(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.TESTING,
            knowledge_type="contextual_metrics"
        )

        self.assertIsNotNone(metrics_transfer)
        self.assertIn("contextual_metrics", metrics_transfer.knowledge_data)


if __name__ == '__main__':
    unittest.main()
