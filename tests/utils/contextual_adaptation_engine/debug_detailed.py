#!/usr/bin/env python3

import sys
import os

# Añadir el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

def debug_detailed_recommendations():
    engine = ContextualAdaptationEngine()
    
    target_context = ContextType.PRODUCTION
    print(f"Target context: {target_context.value}")
    
    recommendations = []
    
    # Evaluar todos los contextos origen posibles
    for source_context in ContextType:
        print(f"\n--- Evaluando source_context: {source_context.value} ---")
        
        if source_context == target_context:
            print("  Saltando (mismo contexto)")
            continue
        
        # Calcular potencial de transferencia
        potential = engine._calculate_transfer_potential(source_context, target_context)
        print(f"  Potential: {potential}")
        
        if potential > 0.1:  # Umbral mínimo
            print(f"  Potencial supera umbral")
            
            # Calcular compatibilidad
            compatibility = engine._validate_context_compatibility(source_context, target_context)
            print(f"  Compatibility: {compatibility}")
            
            # Verificar eficiencia mínima
            estimated_efficiency = engine._get_historical_compatibility(source_context, target_context)
            print(f"  Estimated efficiency: {estimated_efficiency}")
            
            if estimated_efficiency < 0.0:  # min_efficiency por defecto
                print(f"  Eficiencia ({estimated_efficiency}) < min_efficiency (0.0) - CONTINUANDO")
                continue
            
            print(f"  Eficiencia OK")
            
            # Calcular urgencia basada en necesidad
            urgency = engine._calculate_transfer_urgency(target_context, "success_patterns")
            print(f"  Urgency: {urgency}")
            
            # Calcular prioridad general
            priority = (
                compatibility * 0.4 +
                potential * 0.3 +
                estimated_efficiency * 0.2 +
                urgency * 0.1
            )
            print(f"  Priority: {priority}")
            
            # Verificar que la transferencia es realmente ejecutable
            knowledge_types = engine._get_available_knowledge_types(source_context)
            print(f"  Knowledge types: {knowledge_types}")
            
            if not knowledge_types:
                # Si no hay datos históricos, permitir la transferencia con tipo genérico
                knowledge_types = ["success_patterns"]
                print(f"  Usando fallback: {knowledge_types}")
            
            # Crear recomendación
            recommendation = {
                "source_context": source_context.value,
                "target_context": target_context.value,
                "knowledge_type": "success_patterns",
                "compatibility": compatibility,
                "transfer_potential": potential,
                "expected_efficiency": estimated_efficiency,
                "urgency": urgency,
                "priority": priority,
                "recommended_strategy": "adaptive",
                "confidence": min(1.0, priority + 0.1),
                "reasoning": engine._generate_recommendation_reasoning(
                    source_context, target_context, "success_patterns", compatibility, priority
                ),
                "timestamp": "2026-10-04T03:48:00.000000"  # Dummy timestamp
            }
            
            recommendations.append(recommendation)
            print(f"  Recomendación creada")
        else:
            print(f"  Potencial ({potential}) <= umbral (0.1)")
    
    print(f"\n=== Resumen ===")
    print(f"Total recomendaciones generadas: {len(recommendations)}")
    
    if recommendations:
        for i, rec in enumerate(recommendations):
            print(f"\nRecomendación {i+1}: {rec['source_context']} -> {rec['target_context']}")
            print(f"  Priority: {rec['priority']:.3f}")
            print(f"  Reasoning: {rec['reasoning'][:100]}...")
    else:
        print("No se generó ninguna recomendación")

if __name__ == "__main__":
    debug_detailed_recommendations()