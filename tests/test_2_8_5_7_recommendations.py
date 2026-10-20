"""
Tests para 2.8.5.7 — RECOMENDACIONES

Objetivo: Generar recomendación usando datos existentes, verificar compatibilidad,
evitar recomendar transferencias no ejecutables e integrar con ContextualAdaptationEngine.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Añadir el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType


class Test2_8_5_7_Recommendations(unittest.TestCase):
    """Tests para la unidad 2.8.5.7 - RECOMENDACIONES"""
    
    def setUp(self):
        """Configuración inicial para cada test"""
        self.engine = ContextualAdaptationEngine()
        
        # Limpiar la base de conocimiento para tests limpios
        if "transfer_recommendations" in self.engine.knowledge_base:
            del self.engine.knowledge_base["transfer_recommendations"]
    
    def test_2_8_5_7_1_generar_recomendacion_usando_datos_existentes(self):
        """2.8.5.7.1 Generar recomendación usando datos existentes"""
        # Verificar que la función existe y es llamada
        self.assertTrue(hasattr(self.engine, 'get_transfer_recommendations'))
        self.assertTrue(callable(self.engine.get_transfer_recommendations))
        
        # Generar recomendaciones usando datos existentes
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=3
        )
        
        # Verificar que devuelve una lista
        self.assertIsInstance(recommendations, list)
        
        # Verificar estructura básica de cada recomendación
        for recommendation in recommendations:
            self.assertIn("source_context", recommendation)
            self.assertIn("target_context", recommendation)
            self.assertIn("knowledge_type", recommendation)
            self.assertIn("compatibility", recommendation)
            self.assertIn("transfer_potential", recommendation)
            self.assertIn("expected_efficiency", recommendation)
            self.assertIn("urgency", recommendation)
            self.assertIn("priority", recommendation)
            self.assertIn("recommended_strategy", recommendation)
            self.assertIn("confidence", recommendation)
            self.assertIn("reasoning", recommendation)
            self.assertIn("timestamp", recommendation)
            
            # Verificar que los valores son del tipo correcto
            self.assertIsInstance(recommendation["compatibility"], float)
            self.assertIsInstance(recommendation["transfer_potential"], float)
            self.assertIsInstance(recommendation["expected_efficiency"], float)
            self.assertIsInstance(recommendation["urgency"], float)
            self.assertIsInstance(recommendation["priority"], float)
            self.assertIsInstance(recommendation["confidence"], float)
            self.assertIsInstance(recommendation["reasoning"], str)
            self.assertIsInstance(recommendation["timestamp"], str)
    
    def test_2_8_5_7_2_verificar_compatibilidad(self):
        """2.8.5.7.2 Verificar compatibilidad"""
        # Generar recomendaciones
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=5
        )
        
        # Verificar que todas las recomendaciones tienen compatibilidad válida
        for recommendation in recommendations:
            compatibility = recommendation["compatibility"]
            self.assertGreaterEqual(compatibility, 0.0)
            self.assertLessEqual(compatibility, 1.0)
            
            # Verificar que el razonamiento menciona compatibilidad
            reasoning = recommendation["reasoning"]
            self.assertIn("compatibilidad", reasoning.lower())
    
    def test_2_8_5_7_3_evitar_recomendar_transferencias_no_ejecutables(self):
        """2.8.5.7.3 Evitar recomendar transferencias no ejecutables"""
        # Probar con límite de recomendaciones para filtrar automáticamente
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=1  # Límite estricto para filtrar
        )
        
        # Con un límite tan bajo, es probable que no haya recomendaciones
        # o que solo las de mayor prioridad aparezcan
        self.assertIsInstance(recommendations, list)
        
        # Si hay recomendaciones, verificar que cumplan el umbral de prioridad
        for recommendation in recommendations:
            self.assertGreaterEqual(recommendation["priority"], 0.5)
            
            # Verificar que el razonamiento explica por qué es recomendable
            reasoning = recommendation["reasoning"]
            self.assertTrue(len(reasoning) > 10, "El razonamiento debe ser informativo")
    
    def test_2_8_5_7_4_integrar_con_contextual_adaptation_engine(self):
        """2.8.5.7.4 Integrar con ContextualAdaptationEngine"""
        # Verificar que el motor tiene acceso a los datos necesarios
        self.assertIn("knowledge_base", self.engine.__dict__)
        
        # Generar recomendaciones
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=2
        )
        
        # Verificar que las recomendaciones se guardan en la base de conocimiento
        self.assertIn("transfer_recommendations", self.engine.knowledge_base)
        
        stored_recommendations = self.engine.knowledge_base["transfer_recommendations"]
        self.assertIsInstance(stored_recommendations, list)
        
        # Verificar que las recomendaciones guardadas tienen el formato correcto
        for stored_rec in stored_recommendations:
            self.assertIn("source_context", stored_rec)
            self.assertIn("target_context", stored_rec)
            self.assertIn("knowledge_type", stored_rec)
            self.assertIn("generated_timestamp", stored_rec)
    
    def test_2_8_5_7_5_ordenacion_por_prioridad(self):
        """2.8.5.7.5 Verificar que las recomendaciones están ordenadas por prioridad"""
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=5
        )
        
        if len(recommendations) > 1:
            # Verificar que están ordenadas de mayor a menor prioridad
            priorities = [rec["priority"] for rec in recommendations]
            for i in range(len(priorities) - 1):
                self.assertGreaterEqual(priorities[i], priorities[i + 1])
    
    def test_2_8_5_7_6_limitar_numero_de_recomendaciones(self):
        """2.8.5.7.6 Verificar que se respeta el límite de recomendaciones"""
        # Probar con límite de 2 recomendaciones
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=2
        )
        
        self.assertLessEqual(len(recommendations), 2)
    
    def test_2_8_5_7_7_tipos_de_conocimiento_evaluados(self):
        """2.8.5.7.7 Verificar que se evalúan los tipos de conocimiento correctos"""
        # Verificar que los tipos de conocimiento son los esperados
        expected_types = ["success_patterns", "adaptation_strategies", "performance_baselines", "contextual_metrics"]
        
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=5
        )
        
        # Verificar que todas las recomendaciones usan tipos conocidos
        for recommendation in recommendations:
            self.assertIn(recommendation["knowledge_type"], expected_types)
    
    def test_2_8_5_7_8_manejo_de_errores(self):
        """2.8.5.7.8 Verificar manejo de errores"""
        # Probar con parámetros inválidos
        with patch.object(self.engine, '_validate_context_compatibility') as mock_validate:
            mock_validate.side_effect = Exception("Error de compatibilidad")
            
            recommendations = self.engine.get_transfer_recommendations(
                target_context=ContextType.PRODUCTION,
                max_recommendations=3
            )
            
            # Debería devolver una lista vacía o manejada
            self.assertIsInstance(recommendations, list)
    
    def test_2_8_5_7_9_confianza_y_razonamiento(self):
        """2.8.5.7.9 Verificar que la confianza y razonamiento son consistentes"""
        recommendations = self.engine.get_transfer_recommendations(
            target_context=ContextType.PRODUCTION,
            max_recommendations=3
        )
        
        for recommendation in recommendations:
            # Verificar que la confianza es coherente con la prioridad
            expected_confidence = min(1.0, recommendation["priority"] + 0.1)
            self.assertAlmostEqual(recommendation["confidence"], expected_confidence, places=5)
            
            # Verificar que el razonamiento es relevante
            reasoning = recommendation["reasoning"]
            self.assertTrue(len(reasoning) > 20, "El razonamiento debe ser detallado")
            
            # Verificar que menciona los componentes relevantes
            source = recommendation["source_context"]
            target = recommendation["target_context"]
            knowledge_type = recommendation["knowledge_type"]
            
            self.assertIn(source, reasoning)
            self.assertIn(target, reasoning)
            self.assertIn(knowledge_type, reasoning)


if __name__ == '__main__':
    unittest.main()
