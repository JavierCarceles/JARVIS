#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType
import logging

# Configurar logging básico
logging.basicConfig(level=logging.INFO)

def test_recommendations_output():
    """Test para ver qué está realmente devolviendo get_transfer_recommendations"""
    
    # Crear instancia del motor
    engine = ContextualAdaptationEngine()
    
    print("=== Probando get_transfer_recommendations ===")
    
    # Obtener recomendaciones
    recommendations = engine.get_transfer_recommendations(
        target_context=ContextType.PRODUCTION,
        max_recommendations=2
    )
    
    print(f"Devueltas {len(recommendations)} recomendaciones")
    
    for i, rec in enumerate(recommendations):
        print(f"\nRecomendación {i+1}:")
        print(f"  Campos: {list(rec.keys())}")
        print(f"  source_context: {rec.get('source_context', 'MISSING')}")
        print(f"  target_context: {rec.get('target_context', 'MISSING')}")
        print(f"  knowledge_type: {rec.get('knowledge_type', 'MISSING')}")
        print(f"  compatibility: {rec.get('compatibility', 'MISSING')}")
        print(f"  compatibility_score: {rec.get('compatibility_score', 'MISSING')}")
        print(f"  confidence: {rec.get('confidence', 'MISSING')}")
        print(f"  priority: {rec.get('priority', 'MISSING')}")
        print(f"  reasoning: {rec.get('reasoning', 'MISSING')}")
        
    # Verificar knowledge base
    print(f"\n=== Knowledge base después de la llamada ===")
    if "transfer_recommendations" in engine.knowledge_base:
        stored = engine.knowledge_base["transfer_recommendations"]
        print(f"Almacenadas {len(stored)} recomendaciones")
        for i, rec in enumerate(stored[:2]):  # Mostrar solo las primeras 2
            print(f"  Stored {i+1}: {list(rec.keys())}")
    else:
        print("No se encontraron transfer_recommendations en knowledge_base")

if __name__ == "__main__":
    test_recommendations_output()