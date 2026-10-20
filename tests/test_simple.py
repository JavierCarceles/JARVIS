#!/usr/bin/env python3
"""
Test simple para verificar los métodos de estrategia
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

def test_methods():
    engine = ContextualAdaptationEngine()
    
    print("Métodos disponibles en ContextualAdaptationEngine:")
    all_methods = [m for m in dir(engine) if not m.startswith('__')]
    print(f"Total métodos: {len(all_methods)}")
    
    strategy_methods = [m for m in all_methods if 'strategy' in m.lower()]
    print(f"Métodos con 'strategy': {strategy_methods}")
    
    available_methods = [m for m in all_methods if 'available' in m.lower()]
    print(f"Métodos con 'available': {available_methods}")
    
    candidate_methods = [m for m in all_methods if 'candidate' in m.lower()]
    print(f"Métodos con 'candidate': {candidate_methods}")
    
    validate_methods = [m for m in all_methods if 'validate' in m.lower()]
    print(f"Métodos con 'validate': {validate_methods}")
    
    # Verificar específicamente los métodos que necesitamos
    methods_to_check = [
        'get_available_strategies',
        'generate_strategy_candidates', 
        'validate_candidate_strategy',
        '_calculate_strategy_applicability'
    ]
    
    print("\nVerificación de métodos específicos:")
    for method in methods_to_check:
        exists = hasattr(engine, method)
        print(f"  {method}: {'✓' if exists else '✗'}")
        
    # Intentar llamar a get_available_strategies
    try:
        strategies = engine.get_available_strategies(ContextType.DEVELOPMENT)
        print(f"\nget_available_strategies ejecutado correctamente, retornó: {len(strategies)} estrategias")
    except Exception as e:
        print(f"\nError al ejecutar get_available_strategies: {e}")

if __name__ == "__main__":
    test_methods()