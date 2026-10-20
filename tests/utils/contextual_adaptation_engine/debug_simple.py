#!/usr/bin/env python3

import sys
import os

# Añadir el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

def debug_simple_recommendations():
    engine = ContextualAdaptationEngine()
    
    # Probar directamente el método público
    print("=== Probando método público get_transfer_recommendations ===")
    
    recommendations = engine.get_transfer_recommendations(
        target_context=ContextType.PRODUCTION,
        max_recommendations=3
    )
    
    print(f"Recomendaciones devueltas: {len(recommendations)}")
    
    if recommendations:
        for i, rec in enumerate(recommendations):
            print(f"\nRecomendación {i+1}:")
            print(f"  Source: {rec.get('source_context', 'N/A')}")
            print(f"  Target: {rec.get('target_context', 'N/A')}")
            print(f"  Priority: {rec.get('priority', 'N/A')}")
            print(f"  Confidence: {rec.get('confidence', 'N/A')}")
    else:
        print("No se recibieron recomendaciones")

if __name__ == "__main__":
    debug_simple_recommendations()