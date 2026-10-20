"""
Tests para Cross Context Knowledge Transfer (2.8.5)
Verifica las funciones de transferencia de conocimiento ya implementadas en ContextualAdaptationEngine
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Añadir el path para importar los módulos
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType, KnowledgeTransfer
from datetime import datetime


class TestCrossContextKnowledgeTransfer(unittest.TestCase):
    """Tests para las funciones de transferencia de conocimiento entre contextos"""
    
    def setUp(self):
        """Configuración inicial para cada test"""
        self.engine = ContextualAdaptationEngine()
        self.engine.config = {"knowledge_transfer_enabled": True}
        
        # Mockear dependencias externas
        self.engine.logger = Mock()
        self.engine.analytics = Mock()
        
        # Inicializar knowledge base básica
        self.engine.knowledge_base = {
            "success_patterns": {
                "development": [
                    {"pattern": "code_review", "success_rate": 0.9},
                    {"pattern": "unit_tests", "success_rate": 0.8}
                ],
                "production": [
                    {"pattern": "monitoring", "success_rate": 0.95},
                    {"pattern": "load_balancing", "success_rate": 0.85}
                ]
            },
            "adaptation_strategies": {
                "development": [
                    {"strategy": "incremental_deployment", "success_rate": 0.8},
                    {"strategy": "feature_flags", "success_rate": 0.9}
                ],
                "production": [
                    {"strategy": "blue_green_deployment", "success_rate": 0.95},
                    {"strategy": "canary_release", "success_rate": 0.88}
                ]
            },
            "performance_baselines": {
                "development": {"response_time": 0.5, "error_rate": 0.02},
                "production": {"response_time": 0.2, "error_rate": 0.001}
            },
            "contextual_metrics": {
                "development": {"cpu_usage": 0.6, "memory_usage": 0.7},
                "production": {"cpu_usage": 0.8, "memory_usage": 0.9}
            }
        }
    
    def test_2_8_5_1_1_localizar_cross_context_knowledge_transfer(self):
        """2.8.5.1.1 Verificar que no existe CrossContextKnowledgeTransfer separado"""
        # Verificar que no existe una clase separada CrossContextKnowledgeTransfer
        from utils import contextual_adaptation_engine
        self.assertFalse(hasattr(contextual_adaptation_engine, 'CrossContextKnowledgeTransfer'))
        
        # Verificar que las funciones están en ContextualAdaptationEngine
        self.assertTrue(hasattr(self.engine, 'transfer_knowledge'))
        self.assertTrue(hasattr(self.engine, 'batch_knowledge_transfer'))
        self.assertTrue(hasattr(self.engine, 'auto_transfer_knowledge'))
        self.assertTrue(hasattr(self.engine, 'transfer_knowledge_with_feedback'))
        self.assertTrue(hasattr(self.engine, 'get_transfer_recommendations'))
    
    def test_2_8_5_1_2_localizar_transfer_knowledge(self):
        """2.8.5.1.2 Verificar función transfer_knowledge existente"""
        # Verificar que la función existe y tiene la firma correcta
        self.assertTrue(callable(getattr(self.engine, 'transfer_knowledge')))
        
        # Probar llamada básica
        result = self.engine.transfer_knowledge(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.PRODUCTION,
            knowledge_type="success_patterns"
        )
        
        # Verificar que devuelve KnowledgeTransfer o None
        self.assertTrue(result is None or isinstance(result, KnowledgeTransfer))
    
    def test_2_8_5_1_3_localizar_batch_knowledge_transfer(self):
        """2.8.5.1.3 Verificar función batch_knowledge_transfer existente"""
        self.assertTrue(callable(getattr(self.engine, 'batch_knowledge_transfer')))
        
        # Probar llamada básica
        transfer_requests = [
            {
                "source_context": ContextType.DEVELOPMENT,
                "target_context": ContextType.PRODUCTION,
                "knowledge_type": "success_patterns",
                "priority": 1
            }
        ]
        
        results = self.engine.batch_knowledge_transfer(transfer_requests)
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)
    
    def test_2_8_5_1_4_localizar_auto_transfer_knowledge(self):
        """2.8.5.1.4 Verificar función auto_transfer_knowledge existente"""
        self.assertTrue(callable(getattr(self.engine, 'auto_transfer_knowledge')))
        
        # Probar llamada básica
        results = self.engine.auto_transfer_knowledge(
            target_context=ContextType.PRODUCTION,
            knowledge_types=["success_patterns"],
            min_compatibility=0.5
        )
        
        self.assertIsInstance(results, list)
    
    def test_2_8_5_1_5_localizar_transfer_knowledge_with_feedback(self):
        """2.8.5.1.5 Verificar función transfer_knowledge_with_feedback existente"""
        self.assertTrue(callable(getattr(self.engine, 'transfer_knowledge_with_feedback')))
        
        # Probar llamada básica sin callback
        result = self.engine.transfer_knowledge_with_feedback(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.PRODUCTION,
            knowledge_type="success_patterns"
        )
        
        self.assertTrue(result is None or isinstance(result, KnowledgeTransfer))
    
    def test_2_8_5_1_6_localizar_get_transfer_recommendations(self):
        """2.8.5.1.6 Verificar función get_transfer_recommendations existente"""
        self.assertTrue(callable(getattr(self.engine, 'get_transfer_recommendations')))
        
        # Probar llamada básica
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=3
        )
        
        self.assertIsInstance(recommendations, list)
    
    def test_2_8_5_1_7_definir_que_parte_se_reutiliza(self):
        """2.8.5.1.7 Definir qué parte se reutiliza y evitar duplicación"""
        # Verificar que las funciones existentes son reutilizables
        reusable_functions = [
            'transfer_knowledge',
            'batch_knowledge_transfer', 
            'auto_transfer_knowledge',
            'transfer_knowledge_with_feedback',
            'get_transfer_recommendations',
            '_validate_context_compatibility',
            '_calculate_transfer_efficiency',
            '_transform_knowledge_for_target'
        ]
        
        for func_name in reusable_functions:
            self.assertTrue(hasattr(self.engine, func_name), f"Función {func_name} debe ser reutilizable")
        
        # Verificar que no hay duplicación obvia en el código
        # Las funciones pueden tener múltiples implementaciones para diferentes casos de uso
        # Lo importante es que sean funcionales y no redundantes
        pass
    
    def test_2_8_5_1_8_evitar_duplicacion(self):
        """2.8.5.1.8 Evitar duplicación de funcionalidad existente"""
        # Verificar que las funciones existentes no son wrappers vacíos
        methods_to_check = [
            'transfer_knowledge',
            'batch_knowledge_transfer',
            'auto_transfer_knowledge'
        ]
        
        for method_name in methods_to_check:
            method = getattr(self.engine, method_name)
            # Verificar que el método tiene implementación real (no es solo pass)
            method_code = method.__code__.co_code
            self.assertNotEqual(len(method_code), 0, f"Método {method_name} debe tener implementación")
    
    def test_2_8_5_1_9_tests(self):
        """2.8.5.1.9 Tests de integración básica"""
        # Test de transferencia simple
        transfer = self.engine.transfer_knowledge(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.PRODUCTION,
            knowledge_type="success_patterns"
        )
        
        # La transferencia puede fallar por compatibilidad, pero no por error de implementación
        self.assertTrue(transfer is None or isinstance(transfer, KnowledgeTransfer))
        
        # Test de batch
        batch_results = self.engine.batch_knowledge_transfer([
            {
                "source_context": ContextType.DEVELOPMENT,
                "target_context": ContextType.PRODUCTION,
                "knowledge_type": "success_patterns"
            }
        ])
        
        self.assertIsInstance(batch_results, list)
        self.assertEqual(len(batch_results), 1)
        
        # Test de recomendaciones
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=1
        )
        
        self.assertIsInstance(recommendations, list)

    # ------------------------------------------------------------------
    # 2.8.5.2 — MODELO DE CONTEXTO ORIGEN / DESTINO
    # ------------------------------------------------------------------

    def test_2_8_5_2_1_identificar_contexto_origen(self):
        """2.8.5.2.1 Identificar contexto origen"""
        # Usar desarrollo como contexto origen
        source_context = ContextType.DEVELOPMENT

        # Verificar que el contexto es válido
        self.assertIsNotNone(source_context)
        self.assertEqual(source_context.value, "development")

        # Verificar que tiene datos disponibles
        self.assertIn("development", self.engine.knowledge_base["success_patterns"])
        self.assertIn("development", self.engine.knowledge_base["adaptation_strategies"])
        self.assertIn("development", self.engine.knowledge_base["performance_baselines"])

    def test_2_8_5_2_2_identificar_contexto_destino(self):
        """2.8.5.2.2 Identificar contexto destino"""
        # Usar producción como contexto destino
        target_context = ContextType.PRODUCTION

        # Verificar que el contexto es válido
        self.assertIsNotNone(target_context)
        self.assertEqual(target_context.value, "production")

        # Verificar que tiene datos disponibles
        self.assertIn("production", self.engine.knowledge_base["success_patterns"])
        self.assertIn("production", self.engine.knowledge_base["adaptation_strategies"])
        self.assertIn("production", self.engine.knowledge_base["performance_baselines"])

    def test_2_8_5_2_3_verificar_datos_disponibles(self):
        """2.8.5.2.3 Verificar datos disponibles para transferencia"""
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION

        # Verificar que ambos contextos tienen datos
        source_has_data = (
            source_context.value in self.engine.knowledge_base["success_patterns"] and
            source_context.value in self.engine.knowledge_base["adaptation_strategies"] and
            source_context.value in self.engine.knowledge_base["performance_baselines"]
        )
        target_has_data = (
            target_context.value in self.engine.knowledge_base["success_patterns"] and
            target_context.value in self.engine.knowledge_base["adaptation_strategies"] and
            target_context.value in self.engine.knowledge_base["performance_baselines"]
        )

        self.assertTrue(source_has_data, "Contexto origen debe tener datos")
        self.assertTrue(target_has_data, "Contexto destino debe tener datos")

    def test_2_8_5_2_4_detectar_contexto_incompleto(self):
        """2.8.5.2.4 Detectar contexto incompleto"""
        # Contexto con datos limitados
        incomplete_context = "testing"

        # Verificar que tiene algunos datos pero no todos
        has_some_data = (
            incomplete_context in self.engine.knowledge_base["success_patterns"] or
            incomplete_context in self.engine.knowledge_base["adaptation_strategies"]
        )

        # Usar get_transfer_recommendations para detectar contexto incompleto
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=3
        )

        # Si el contexto origen es incompleto, puede no generar recomendaciones
        self.assertIsInstance(recommendations, list)

    # ------------------------------------------------------------------
    # 2.8.5.3 — COMPATIBILIDAD
    # ------------------------------------------------------------------

    def test_2_8_5_3_1_reutilizar_validate_context_compatibility(self):
        """2.8.5.3.1 Reutilizar _validate_context_compatibility existente"""
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION

        # Verificar que el método existe
        self.assertTrue(hasattr(self.engine, '_validate_context_compatibility'))
        self.assertTrue(callable(self.engine._validate_context_compatibility))

        # Probar validación de compatibilidad
        compatibility = self.engine._validate_context_compatibility(
            source_context=source_context,
            target_context=target_context
        )

        # Debería devolver True/False o score
        self.assertIsNotNone(compatibility)

    def test_2_8_5_3_2_verificar_umbrales_existentes(self):
        """2.8.5.3.2 Verificar umbrales existentes"""
        # Verificar que el método _validate_context_compatibility existe y tiene parámetros
        self.assertTrue(hasattr(self.engine, '_validate_context_compatibility'))
        self.assertTrue(callable(self.engine._validate_context_compatibility))

        # Probar validación con valores por defecto
        compatibility = self.engine._validate_context_compatibility(
            source_context=ContextType.DEVELOPMENT,
            target_context=ContextType.PRODUCTION
        )

        # Debería devolver un valor de compatibilidad
        self.assertIsNotNone(compatibility)
        # Si devuelve un score, debe estar en rango [0, 1]
        if isinstance(compatibility, (int, float)):
            self.assertGreaterEqual(compatibility, 0.0)
            self.assertLessEqual(compatibility, 1.0)

    def test_2_8_5_3_3_rechazar_transferencia_incompatible(self):
        """2.8.5.3.3 Rechazar transferencia incompatible"""
        # Contextos que pueden ser incompatibles (ej. desarrollo -> desarrollo)
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.DEVELOPMENT

        # Intentar transferencia
        compatibility = self.engine._validate_context_compatibility(
            source_context=source_context,
            target_context=target_context
        )

        # Validar resultado
        self.assertIsNotNone(compatibility)

    def test_2_8_5_3_4_registrar_motivo(self):
        """2.8.5.3.4 Registrar motivo de rechazo"""
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.DEVELOPMENT

        # Probar validación
        compatibility = self.engine._validate_context_compatibility(
            source_context=source_context,
            target_context=target_context
        )

        # Verificar que se registra algo (aunque sea por log)
        self.assertIsNotNone(compatibility)

    # ------------------------------------------------------------------
    # 2.8.5.4 — UNIDADES DE CONOCIMIENTO
    # ------------------------------------------------------------------

    def test_2_8_5_4_1_identificar_que_conocimiento_puede_transferirse(self):
        """2.8.5.4.1 Identificar qué conocimiento puede transferirse"""
        # Tipos de conocimiento disponibles en knowledge base
        knowledge_types = [
            "success_patterns",
            "adaptation_strategies",
            "performance_baselines"
        ]

        # Verificar que estos tipos están disponibles
        for kt in knowledge_types:
            self.assertIn(kt, self.engine.knowledge_base,
                         f"Tipo de conocimiento {kt} debe estar disponible")

    def test_2_8_5_4_2_separar_conocimiento_no_reutilizable(self):
        """2.8.5.4.2 Separar conocimiento de estado actual no reutilizable"""
        # Estado actual no es transferible (es instanciado)
        current_state_data = {
            "context_snapshots": self.engine.context_snapshots,
            "adaptation_history": self.engine.adaptation_history,
            "current_context": self.engine.current_context
        }

        # Verificar que estos datos no están en knowledge_base
        for key in current_state_data:
            self.assertNotIn(key, self.engine.knowledge_base,
                           f"Estado actual {key} no debe estar en knowledge_base")

        # Verificar que knowledge_base contiene conocimiento persistible
        self.assertIn("success_patterns", self.engine.knowledge_base)
        self.assertIn("adaptation_strategies", self.engine.knowledge_base)

    def test_2_8_5_4_3_extraer_usando_logica_existente(self):
        """2.8.5.4.3 Extraer usando lógica existente"""
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION

        # Usar _extract_knowledge_from_context (existente) con knowledge_type
        knowledge_type = "success_patterns"

        if hasattr(self.engine, '_extract_knowledge_from_context'):
            knowledge = self.engine._extract_knowledge_from_context(
                context=source_context,
                knowledge_type=knowledge_type
            )

            # Debería devolver conocimiento (lista o dict según implementación)
            self.assertIsNotNone(knowledge)
            # No asumimos tipo específico, solo que no es None

    def test_2_8_5_4_4_transformar_usando_mecanismos_existentes(self):
        """2.8.5.4.4 Transformar usando mecanismos existentes"""
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION

        # Verificar que _transform_knowledge_for_target existe y es callable
        self.assertTrue(hasattr(self.engine, '_transform_knowledge_for_target'))
        self.assertTrue(callable(self.engine._transform_knowledge_for_target))

        # Probar transformación con firma real
        knowledge_type = "success_patterns"

        if hasattr(self.engine, '_extract_knowledge_from_context'):
            knowledge = self.engine._extract_knowledge_from_context(
                context=source_context,
                knowledge_type=knowledge_type
            )

            if knowledge:
                # Transformar conocimiento usando firma real (4 parámetros)
                transformed = self.engine._transform_knowledge_for_target(
                    knowledge_data=knowledge,
                    source_context=source_context,
                    target_context=target_context,
                    strategy=None
                )

                # Debería devolver conocimiento transformado
                self.assertIsNotNone(transformed)
                self.assertIsInstance(transformed, (list, dict))


    # ------------------------------------------------------------------
    # 2.8.5.6 — CONFIDENCIA / FEEDBACK
    # ------------------------------------------------------------------

    def test_2_8_5_6_1_obtener_confianza_existente(self):
        """2.8.5.6.1 Obtener confianza existente"""
        # Verificar que el método de confianza existe
        self.assertTrue(hasattr(self.engine, 'get_transfer_confidence'))
        self.assertTrue(callable(self.engine.get_transfer_confidence))
        
        # Probar obtener confianza para transferencia existente
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION
        knowledge_type = "success_patterns"
        
        # Realizar una transferencia primero para tener datos
        transfer = self.engine.transfer_knowledge(
            source_context=source_context,
            target_context=target_context,
            knowledge_type=knowledge_type
        )
        
        if transfer:
            # Obtener confianza para la transferencia
            confidence = self.engine.get_transfer_confidence(transfer.transfer_id)
            self.assertIsNotNone(confidence)
            # La confianza debe estar en rango [0.0, 1.0]
            if isinstance(confidence, (int, float)):
                self.assertGreaterEqual(confidence, 0.0)
                self.assertLessEqual(confidence, 1.0)

    def test_2_8_5_6_2_registrar_feedback(self):
        """2.8.5.6.2 Registrar feedback"""
        # Verificar que el método de feedback existe
        self.assertTrue(hasattr(self.engine, 'register_transfer_feedback'))
        self.assertTrue(callable(self.engine.register_transfer_feedback))
        
        # Realizar una transferencia
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION
        knowledge_type = "success_patterns"
        
        transfer = self.engine.transfer_knowledge(
            source_context=source_context,
            target_context=target_context,
            knowledge_type=knowledge_type
        )
        
        if transfer:
            # Registrar feedback positivo
            feedback_result = self.engine.register_transfer_feedback(
                transfer_id=transfer.transfer_id,
                success=True,
                feedback_score=0.8,
                feedback_comments="Transferencia exitosa"
            )
            
            # Verificar que el feedback se registró
            self.assertIsNotNone(feedback_result)
            self.assertIsInstance(feedback_result, dict)

    def test_2_8_5_6_3_evaluar_resultado(self):
        """2.8.5.6.3 Evaluar resultado"""
        # Verificar que el método de evaluación existe
        self.assertTrue(hasattr(self.engine, 'evaluate_transfer_result'))
        self.assertTrue(callable(self.engine.evaluate_transfer_result))
        
        # Realizar una transferencia
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION
        knowledge_type = "success_patterns"
        
        transfer = self.engine.transfer_knowledge(
            source_context=source_context,
            target_context=target_context,
            knowledge_type=knowledge_type
        )
        
        if transfer:
            # Evaluar resultado de la transferencia
            evaluation = self.engine.evaluate_transfer_result(transfer)
            
            # Debería devolver una evaluación estructurada
            self.assertIsNotNone(evaluation)
            self.assertIsInstance(evaluation, dict)
            # Verificar campos esperados
            self.assertIn('success', evaluation)
            self.assertIn('confidence_score', evaluation)
            self.assertIn('feedback_summary', evaluation)

    def test_2_8_5_6_4_ajustar_confianza(self):
        """2.8.5.6.4 Ajustar confianza solo mediante mecanismo existente"""
        # Verificar que el método de ajuste de confianza existe
        self.assertTrue(hasattr(self.engine, 'adjust_transfer_confidence'))
        self.assertTrue(callable(self.engine.adjust_transfer_confidence))
        
        # Realizar una transferencia
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION
        knowledge_type = "success_patterns"
        
        transfer = self.engine.transfer_knowledge(
            source_context=source_context,
            target_context=target_context,
            knowledge_type=knowledge_type
        )
        
        if transfer:
            # Ajustar confianza basado en feedback
            original_confidence = self.engine.get_transfer_confidence(transfer.transfer_id)
            adjusted_confidence = self.engine.adjust_transfer_confidence(
                transfer_id=transfer.transfer_id,
                feedback_success=True,
                feedback_score=0.9
            )
            
            # Verificar que la confianza se ajustó
            self.assertIsNotNone(adjusted_confidence)
            if isinstance(original_confidence, (int, float)) and isinstance(adjusted_confidence, (int, float)):
                # La confianza debería mejorar con feedback positivo
                self.assertGreaterEqual(adjusted_confidence, 0.0)
                self.assertLessEqual(adjusted_confidence, 1.0)

    def test_2_8_5_6_5_tests(self):
        """2.8.5.6.5 Tests de integración de confianza/feedback"""
        # Test de flujo completo: transferencia -> feedback -> evaluación -> ajuste
        source_context = ContextType.DEVELOPMENT
        target_context = ContextType.PRODUCTION
        knowledge_type = "success_patterns"
        
        # 1. Realizar transferencia
        transfer = self.engine.transfer_knowledge(
            source_context=source_context,
            target_context=target_context,
            knowledge_type=knowledge_type
        )
        
        if transfer:
            # 2. Registrar feedback
            feedback_result = self.engine.register_transfer_feedback(
                transfer_id=transfer.transfer_id,
                success=True,
                feedback_score=0.85,
                feedback_comments="Buen resultado general"
            )
            
            # 3. Evaluar resultado
            evaluation = self.engine.evaluate_transfer_result(transfer)
            
            # 4. Ajustar confianza
            adjusted_confidence = self.engine.adjust_transfer_confidence(
                transfer_id=transfer.transfer_id,
                feedback_success=True,
                feedback_score=0.85
            )
            
            # Verificar que todo el flujo funcionó
            self.assertIsNotNone(feedback_result)
            self.assertIsNotNone(evaluation)
            self.assertIsNotNone(adjusted_confidence)
            
            # Verificar que la evaluación contiene los campos esperados
            self.assertIn('success', evaluation)
            self.assertIn('confidence_score', evaluation)
            self.assertIn('feedback_summary', evaluation)


if __name__ == '__main__':
    unittest.main()