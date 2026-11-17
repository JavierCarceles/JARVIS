#!/usr/bin/env python3
"""
Test simple para verificar los metodos de estrategia
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from src.experimental.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

def test_engine_lists_strategy_methods():
    engine = ContextualAdaptationEngine()
    
    print("Metodos disponibles en ContextualAdaptationEngine:")
    all_methods = [m for m in dir(engine) if not m.startswith('__')]
    print(f"Total metodos: {len(all_methods)}")
    
    strategy_methods = [m for m in all_methods if 'strategy' in m.lower()]
    print(f"Metodos con 'strategy': {strategy_methods}")
    
    available_methods = [m for m in all_methods if 'available' in m.lower()]
    print(f"Metodos con 'available': {available_methods}")
    
    candidate_methods = [m for m in all_methods if 'candidate' in m.lower()]
    print(f"Metodos con 'candidate': {candidate_methods}")
    
    validate_methods = [m for m in all_methods if 'validate' in m.lower()]
    print(f"Metodos con 'validate': {validate_methods}")
    
    # Verificar especificamente los metodos que necesitamos
    methods_to_check = [
        'get_available_strategies',
        'generate_strategy_candidates', 
        'validate_candidate_strategy',
        '_calculate_strategy_applicability'
    ]
    
    print("\nVerificacion de metodos especificos:")
    for method in methods_to_check:
        exists = hasattr(engine, method)
        print(f"  {method}: {'[OK]' if exists else '[X]'}")
        
    # Intentar llamar a get_available_strategies
    try:
        strategies = engine.get_available_strategies(ContextType.DEVELOPMENT)
        print(f"\nget_available_strategies ejecutado correctamente, retorno: {len(strategies)} estrategias")
    except Exception as e:
        print(f"\nError al ejecutar get_available_strategies: {e}")

if __name__ == "__main__":
    test_engine_lists_strategy_methods()