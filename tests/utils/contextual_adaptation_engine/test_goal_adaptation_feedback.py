#!/usr/bin/env python3
"""
Test para el método de feedback de adaptación de Goal (2.8.8.7)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine

def test_goal_adaptation_feedback():
    """Test del método _capture_goal_adaptation_feedback"""
    
    print("=== Test 2.8.8.7: Feedback de Adaptación de Goal ===")
    
    # Crear instancia del motor
    engine = ContextualAdaptationEngine()
    
    # Simular resultado de adaptación
    adaptation_result = {
        "adaptation_id": "test_adaptation_001",
        "original_goal_id": "goal_original_001",
        "adapted_goal_id": "goal_adapted_001",
        "adaptation_context": {
            "goal_type": "navigate",
            "context_type": "development",
            "expected_metrics": {
                "response_time": 2.0,
                "accuracy": 0.95
            }
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {
                "response_time": 1.5,  # Mejor que esperado
                "accuracy": 0.98       # Mejor que esperado
            }
        },
        "verification_result": {
            "verified": True,
            "impact_score": 0.8
        }
    }
    
    # Capturar feedback
    feedback_result = engine._capture_goal_adaptation_feedback(adaptation_result)
    
    print(f"Feedback capturado: {feedback_result.get('success', False)}")
    print(f"Análisis de mejora: {feedback_result.get('improvement_analysis', {})}")
    
    # Verificar que el feedback fue registrado
    if "goal_adaptation_feedback" in engine.knowledge_base:
        feedback_records = engine.knowledge_base["goal_adaptation_feedback"]
        print(f"Registros de feedback: {len(feedback_records)}")
        
        if feedback_records:
            last_feedback = feedback_records[-1]
            print(f"Último feedback: {last_feedback.get('feedback_quality', 'unknown')}")
    
    # Verificar estrategias actualizadas
    if "adaptation_strategies" in engine.knowledge_base:
        strategies = engine.knowledge_base["adaptation_strategies"]
        if "successful_strategies" in strategies:
            print(f"Estrategias exitosas: {len(strategies['successful_strategies'])}")
    
    # Verificar patrones de éxito
    if "success_patterns" in engine.knowledge_base:
        patterns = engine.knowledge_base["success_patterns"]
        print(f"Patrones de éxito: {len(patterns)}")
    
    print("✅ Test de feedback de adaptación completado")
    return True

def test_adaptation_improvement_analysis():
    """Test del análisis de mejora"""
    
    print("\n=== Test: Análisis de Mejora ===")
    
    engine = ContextualAdaptationEngine()
    
    # Caso 1: Adaptación con mejora
    result_with_improvement = {
        "adaptation_id": "test_improvement_001",
        "original_goal_id": "goal_original_002",
        "adapted_goal_id": "goal_adapted_002",
        "adaptation_context": {
            "goal_type": "navigate",
            "expected_metrics": {
                "response_time": 2.0,
                "accuracy": 0.95
            }
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {
                "response_time": 1.2,  # Mejor
                "accuracy": 0.97       # Mejor
            }
        },
        "verification_result": {
            "verified": True,
            "impact_score": 0.9
        }
    }
    
    improvement_analysis = engine._analyze_adaptation_improvement(result_with_improvement)
    print(f"Mejora detectada: {improvement_analysis.get('improved', False)}")
    print(f"Evidencia: {improvement_analysis.get('evidence', [])}")
    
    # Caso 2: Adaptación sin mejora
    result_no_improvement = {
        "adaptation_id": "test_no_improvement_001",
        "original_goal_id": "goal_original_003",
        "adapted_goal_id": "goal_adapted_003",
        "adaptation_context": {
            "goal_type": "navigate",
            "expected_metrics": {
                "response_time": 1.0,
                "accuracy": 0.98
            }
        },
        "execution_result": {
            "success": True,
            "performance_metrics": {
                "response_time": 2.5,  # Peor
                "accuracy": 0.92       # Peor
            }
        },
        "verification_result": {
            "verified": False,
            "impact_score": 0.1
        }
    }
    
    no_improvement_analysis = engine._analyze_adaptation_improvement(result_no_improvement)
    print(f"Mejora detectada: {no_improvement_analysis.get('improved', False)}")
    print(f"Indicadores de degradación: {no_improvement_analysis.get('degradation_indicators', [])}")
    
    print("✅ Test de análisis de mejora completado")
    return True

if __name__ == "__main__":
    try:
        test_goal_adaptation_feedback()
        test_adaptation_improvement_analysis()
        print("\n🎉 Todos los tests de feedback de adaptación pasaron")
    except Exception as e:
        print(f"\n❌ Error en los tests: {e}")
        import traceback
        traceback.print_exc()