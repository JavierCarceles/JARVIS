#!/usr/bin/env python3
"""
Test para el bucle de aprendizaje continuo de adaptación de Goal (2.8.8.8)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.adaptive_learning_engine import AdaptiveLearningEngine

def test_goal_adaptation_learning_loop():
    """Test del bucle de aprendizaje continuo para adaptación de Goal"""
    
    print("=== Test 2.8.8.8: Bucle de Aprendizaje Continuo de Adaptación de Goal ===")
    
    # Crear instancia del motor
    engine = AdaptiveLearningEngine()
    
    # Simular múltiples ciclos de feedback acumulado
    feedback_cycles = [
        {
            "adaptation_id": "learning_cycle_001",
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
                    "response_time": 1.8,  # Ligera mejora
                    "accuracy": 0.96
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.7
            }
        },
        {
            "adaptation_id": "learning_cycle_002",
            "original_goal_id": "goal_original_001",
            "adapted_goal_id": "goal_adapted_002",
            "adaptation_context": {
                "goal_type": "navigate",
                "context_type": "development",
                "expected_metrics": {
                    "response_time": 1.8,  # Esperando mejoría
                    "accuracy": 0.96
                }
            },
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 1.5,  # Mejora significativa
                    "accuracy": 0.98
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.9
            }
        },
        {
            "adaptation_id": "learning_cycle_003",
            "original_goal_id": "goal_original_001",
            "adapted_goal_id": "goal_adapted_003",
            "adaptation_context": {
                "goal_type": "navigate",
                "context_type": "development",
                "expected_metrics": {
                    "response_time": 1.5,  # Esperando mantener
                    "accuracy": 0.98
                }
            },
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 1.4,  # Continúa mejorando
                    "accuracy": 0.99
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.95
            }
        }
    ]
    
    # Ejecutar bucle de aprendizaje continuo
    learning_results = []
    for i, feedback_data in enumerate(feedback_cycles):
        print(f"\n--- Ciclo de Aprendizaje {i+1} ---")
        
        # Capturar feedback individual
        feedback_result = engine._capture_feedback(feedback_data)
        learning_results.append(feedback_result)
        
        print(f"Feedback capturado: {feedback_result.get('success', False)}")
        print(f"Análisis de mejora: {feedback_result.get('improvement_analysis', {})}")
        
        # Ejecutar bucle de aprendizaje continuo
        learning_loop_result = engine._execute_learning_loop(feedback_result)
        learning_results.append(learning_loop_result)
        
        print(f"Bucle de aprendizaje ejecutado: {learning_loop_result.get('success', False)}")
        print(f"Patrones aprendidos: {learning_loop_result.get('learned_patterns', [])}")
    
    # Verificar acumulación de aprendizaje
    print("\n=== Verificación de Aprendizaje Acumulado ===")
    
    # Verificar patrones de éxito acumulados
    if "goal_adaptation_feedback" in engine.knowledge_base:
        feedback_records = engine.knowledge_base["goal_adaptation_feedback"]
        print(f"Registros de feedback acumulados: {len(feedback_records)}")
        
        if feedback_records:
            # Calcular tendencia de mejora
            response_times = []
            accuracies = []
            
            for record in feedback_records:
                exec_result = record.get("execution_result", {})
                metrics = exec_result.get("performance_metrics", {})
                
                if "response_time" in metrics:
                    response_times.append(metrics["response_time"])
                if "accuracy" in metrics:
                    accuracies.append(metrics["accuracy"])
            
            if response_times:
                print(f"Tendencia de tiempo de respuesta: {response_times[0]:.2f} -> {response_times[-1]:.2f}")
            if accuracies:
                print(f"Tendencia de precisión: {accuracies[0]:.2f} -> {accuracies[-1]:.2f}")
    
    # Verificar estrategias adaptativas aprendidas
    if "adaptation_strategies" in engine.knowledge_base:
        strategies = engine.knowledge_base["adaptation_strategies"]
        if "successful_strategies" in strategies:
            print(f"Estrategias exitosas aprendidas: {len(strategies['successful_strategies'])}")
            
            for strategy in strategies["successful_strategies"]:
                print(f"  - {strategy.get('strategy_name', 'unknown')}: {strategy.get('success_rate', 0.0):.2f}")
    
    # Verificar patrones de aprendizaje
    if "learning_patterns" in engine.knowledge_base:
        patterns = engine.knowledge_base["learning_patterns"]
        print(f"Patrones de aprendizaje: {len(patterns)}")
        
        for pattern in patterns:
            print(f"  - {pattern.get('pattern_type', 'unknown')}: {pattern.get('confidence', 0.0):.2f}")
    
    print("✅ Test de bucle de aprendizaje continuo completado")
    return True

def test_learning_convergence():
    """Test de convergencia del aprendizaje"""
    
    print("\n=== Test: Convergencia del Aprendizaje ===")
    
    engine = AdaptiveLearningEngine()
    
    # Simular múltiples ciclos con el mismo objetivo para ver convergencia
    goal_id = "convergence_test_goal"
    
    for cycle in range(5):
        feedback_data = {
            "adaptation_id": f"convergence_cycle_{cycle}",
            "original_goal_id": goal_id,
            "adapted_goal_id": f"adapted_goal_{cycle}",
            "adaptation_context": {
                "goal_type": "navigate",
                "context_type": "development",
                "expected_metrics": {
                    "response_time": 2.0 - (cycle * 0.2),  # Mejora progresiva
                    "accuracy": 0.90 + (cycle * 0.02)
                }
            },
            "execution_result": {
                "success": True,
                "performance_metrics": {
                    "response_time": 2.0 - (cycle * 0.3),  # Mejora mayor
                    "accuracy": 0.90 + (cycle * 0.03)
                }
            },
            "verification_result": {
                "verified": True,
                "impact_score": 0.6 + (cycle * 0.08)
            }
        }
        
        # Ejecutar bucle de aprendizaje
        feedback_result = engine._capture_feedback(feedback_data)
        learning_result = engine._execute_learning_loop(feedback_result)
        
        print(f"Ciclo {cycle+1}: Impacto = {learning_result.get('impact_score', 0.0):.2f}")
    
    # Verificar convergencia
    if "goal_adaptation_feedback" in engine.knowledge_base:
        records = engine.knowledge_base["goal_adaptation_feedback"]
        if len(records) >= 2:
            first_impact = records[0].get("verification_result", {}).get("impact_score", 0.0)
            last_impact = records[-1].get("verification_result", {}).get("impact_score", 0.0)
            
            improvement = last_impact - first_impact
            print(f"Mejora total en convergencia: {improvement:.2f}")
            
            if improvement > 0.3:
                print("✅ Convergencia exitosa detectada")
                return True
            else:
                print("⚠️ Convergencia parcial o no detectada")
                return False
    
    return False

def test_learning_adaptation_strategies():
    """Test de estrategias de adaptación aprendidas"""
    
    print("\n=== Test: Estrategias de Adaptación Aprendidas ===")
    
    engine = AdaptiveLearningEngine()
    
    # Simular diferentes tipos de adaptación
    adaptation_scenarios = [
        {
            "adaptation_id": "strategy_test_1",
            "goal_type": "navigate",
            "adaptation_context": {"complexity": "low"},
            "execution_result": {"success": True, "performance_metrics": {"response_time": 1.0}},
            "verification_result": {"verified": True, "impact_score": 0.8}
        },
        {
            "adaptation_id": "strategy_test_2", 
            "goal_type": "navigate",
            "adaptation_context": {"complexity": "medium"},
            "execution_result": {"success": True, "performance_metrics": {"response_time": 1.5}},
            "verification_result": {"verified": True, "impact_score": 0.7}
        },
        {
            "adaptation_id": "strategy_test_3",
            "goal_type": "navigate", 
            "adaptation_context": {"complexity": "high"},
            "execution_result": {"success": True, "performance_metrics": {"response_time": 2.0}},
            "verification_result": {"verified": True, "impact_score": 0.6}
        }
    ]
    
    for scenario in adaptation_scenarios:
        feedback_data = {
            "adaptation_id": scenario["adaptation_id"],
            "original_goal_id": "test_goal",
            "adapted_goal_id": f"adapted_{scenario['adaptation_id']}",
            "adaptation_context": scenario["adaptation_context"],
            "execution_result": scenario["execution_result"],
            "verification_result": scenario["verification_result"]
        }
        
        feedback_result = engine._capture_feedback(feedback_data)
        learning_result = engine._execute_learning_loop(feedback_result)
        
        print(f"Estrategia para {scenario['adaptation_context']['complexity']}: "
              f"impacto = {learning_result.get('impact_score', 0.0):.2f}")
    
    # Verificar estrategias aprendidas
    if "adaptation_strategies" in engine.knowledge_base:
        strategies = engine.knowledge_base["adaptation_strategies"]
        if "successful_strategies" in strategies:
            print(f"Estrategias aprendidas: {len(strategies['successful_strategies'])}")
            
            for strategy in strategies["successful_strategies"]:
                context = strategy.get("context", {})
                strategy_name = strategy.get("strategy_name", "unknown")
                success_rate = strategy.get("success_rate", 0.0)
                
                print(f"  - {strategy_name} para {context}: {success_rate:.2f}")
    
    return True

if __name__ == "__main__":
    # Ejecutar tests
    test_goal_adaptation_learning_loop()
    test_learning_convergence()
    test_learning_adaptation_strategies()
    
    print("\n🎉 Todos los tests del bucle de aprendizaje continuo completados")