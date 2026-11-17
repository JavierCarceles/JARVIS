#!/usr/bin/env python3
"""
Test para el metodo de feedback de adaptacion de Goal (2.8.8.7)

AISLAMIENTO (2.8.8.9.4.6)
El motor se instancia SIEMPRE con `data_dir` temporal. Antes este test
creaba el motor sin `data_dir`, por lo que `_capture_goal_adaptation_feedback`
persistia el feedback en `data/goal_adaptation_feedback.json` de PRODUCCION en
cada ejecucion de la suite (verificado: el fichero crecia en cada ejecucion y
acumulaba registros `test_adaptation_001`). Esa contaminacion invalidaba la
persistencia de Goal y de patrones de produccion, que quedaba compuesta
integramente por datos de test.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from src.experimental.contextual_adaptation_engine import ContextualAdaptationEngine

def test_goal_adaptation_feedback(tmp_path):
    """Test del metodo _capture_goal_adaptation_feedback"""
    
    print("=== Test 2.8.8.7: Feedback de Adaptacion de Goal ===")
    
    # Crear instancia del motor aislada del `data/` de produccion
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    
    # Simular resultado de adaptacion
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
    
    assert feedback_result.get("success") is True, (
        f"El feedback debe capturarse correctamente: {feedback_result.get('error_message')}"
    )
    
    print(f"Feedback capturado: {feedback_result.get('success', False)}")
    print(f"Analisis de mejora: {feedback_result.get('improvement_analysis', {})}")
    
    # Verificar que el feedback fue registrado
    if "goal_adaptation_feedback" in engine.knowledge_base:
        feedback_records = engine.knowledge_base["goal_adaptation_feedback"]
        print(f"Registros de feedback: {len(feedback_records)}")
        
        if feedback_records:
            last_feedback = feedback_records[-1]
            print(f"Ultimo feedback: {last_feedback.get('feedback_quality', 'unknown')}")
    
    # Verificar estrategias actualizadas
    if "adaptation_strategies" in engine.knowledge_base:
        strategies = engine.knowledge_base["adaptation_strategies"]
        if "successful_strategies" in strategies:
            print(f"Estrategias exitosas: {len(strategies['successful_strategies'])}")
    
    # Verificar patrones de exito
    if "success_patterns" in engine.knowledge_base:
        patterns = engine.knowledge_base["success_patterns"]
        print(f"Patrones de exito: {len(patterns)}")
    
    print("[OK] Test de feedback de adaptacion completado")

def test_adaptation_improvement_analysis(tmp_path):
    """Test del analisis de mejora"""
    
    print("\n=== Test: Analisis de Mejora ===")
    
    engine = ContextualAdaptationEngine(data_dir=str(tmp_path))
    
    # Caso 1: Adaptacion con mejora
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
    
    # Assert: improvement should be detected
    assert improvement_analysis.get("improved") is True, (
        "Se esperaba mejora detectada pero improved=False"
    )
    evidence = improvement_analysis.get("evidence", [])
    assert len(evidence) > 0, "Se esperaba evidencia de mejora no vac\u00eda"
    for metric_name, delta in improvement_analysis.get("improvements", {}).items():
        assert delta > 0, f"El delta de mejora para {metric_name} debe ser positivo: {delta}"
    
    # Caso 2: Adaptacion sin mejora
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
    print(f"Evidencia: {no_improvement_analysis.get('evidence', [])}")
    
    # Assert: no improvement should be detected
    assert no_improvement_analysis.get("improved") is False, (
        "Se esperaba que no se detectara mejora pero improved=True"
    )
    evidence = no_improvement_analysis.get("evidence", [])
    assert len(evidence) > 0, "Se esperaba evidencia de detracci\u00f3n no vac\u00eda"
    for metric_name, delta in no_improvement_analysis.get("improvements", {}).items():
        assert delta < 0, f"El delta de {metric_name} debe ser negativo en caso de detracci\u00f3n: {delta}"
    
    print("[OK] Test de analisis de mejora completado")

if __name__ == "__main__":
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as _tmp:
            test_goal_adaptation_feedback(_tmp)
            test_adaptation_improvement_analysis(_tmp)
        print("\n[OK] Todos los tests de feedback de adaptacion pasaron")
    except Exception as e:
        print(f"\n[ERROR] Error en los tests: {e}")
        import traceback
        traceback.print_exc()