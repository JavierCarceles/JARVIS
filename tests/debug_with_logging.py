#!/usr/bin/env python3

import sys
import os

# Añadir el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

def debug_with_logging():
    engine = ContextualAdaptationEngine()
    
    target_context = ContextType.PRODUCTION
    
    results = []
    
    for source_context in ContextType:
        if source_context == target_context:
            results.append(f"Saltando {source_context.value} (mismo contexto)")
            continue
        
        results.append(f"\n--- {source_context.value} -> {target_context.value} ---")
        
        try:
            potential = engine._calculate_transfer_potential(source_context, target_context)
            results.append(f"  Potential: {potential}")
            
            if potential > 0.1:
                compatibility = engine._validate_context_compatibility(source_context, target_context)
                results.append(f"  Compatibility: {compatibility}")
                
                estimated_efficiency = engine._get_historical_compatibility(source_context, target_context)
                results.append(f"  Estimated efficiency: {estimated_efficiency}")
                
                if estimated_efficiency < 0.0:
                    results.append(f"  Skipping: efficiency below threshold")
                    continue
                
                urgency = engine._calculate_transfer_urgency(target_context, "success_patterns")
                results.append(f"  Urgency: {urgency}")
                
                priority = (
                    compatibility * 0.4 +
                    potential * 0.3 +
                    estimated_efficiency * 0.2 +
                    urgency * 0.1
                )
                results.append(f"  Priority: {priority}")
                
                knowledge_types = engine._get_available_knowledge_types(source_context)
                results.append(f"  Knowledge types: {knowledge_types}")
                
                if not knowledge_types:
                    knowledge_types = ["success_patterns"]
                    results.append(f"  Fallback knowledge types: {knowledge_types}")
                
                reasoning = engine._generate_recommendation_reasoning(
                    source_context, target_context, "success_patterns", compatibility, priority
                )
                results.append(f"  Reasoning OK")
                
                results.append(f"  EXITOSO: Se crearia recomendacion")
            else:
                results.append(f"  Skipping: potential below threshold")
                
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            results.append(f"  ERROR: {e}")
            results.append(f"  {tb[-200:] if tb else 'no traceback'}")  # Ultimos 200 chars del traceback
    
    results.append("\n=== Fin del debug ===")
    
    # Escribir resultados a archivo para evitar problemas de encoding
    with open("debug_output.txt", "w", encoding="utf-8") as f:
        for line in results:
            f.write(line + "\n")
    
    print("Debug completado. Ver debug_output.txt")

if __name__ == "__main__":
    debug_with_logging()