#!/usr/bin/env python3
"""
Test para verificar los métodos de la clase ContextualAdaptationEngine
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

# Importar la clase directamente
from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

def test_engine_exposes_strategy_methods():
    print("Creando instancia de ContextualAdaptationEngine...")
    engine = ContextualAdaptationEngine()
    
    print(f"Clase: {engine.__class__.__name__}")
    print(f"ID: {id(engine)}")
    
    # Verificar métodos específicos
    methods_to_check = [
        'get_available_strategies',
        'generate_strategy_candidates', 
        'validate_candidate_strategy',
        '_calculate_strategy_applicability',
        '_validate_context_compatibility'
    ]
    
    print("\nVerificación de métodos:")
    for method in methods_to_check:
        exists = hasattr(engine, method)
        print(f"  {method}: {'EXISTE' if exists else 'NO EXISTE'}")
        
        if exists:
            try:
                # Intentar obtener el método
                method_obj = getattr(engine, method)
                print(f"    Tipo: {type(method_obj)}")
                print(f"    Callable: {callable(method_obj)}")
            except Exception as e:
                print(f"    Error al acceder: {e}")
    
    # Verificar métodos con 'strategy'
    print("\nTodos los métodos con 'strategy':")
    strategy_methods = [m for m in dir(engine) if 'strategy' in m.lower()]
    for method in strategy_methods:
        print(f"  {method}")
    
    # Verificar todos los métodos públicos
    print("\nMétodos públicos (sin '_'):")
    public_methods = [m for m in dir(engine) if not m.startswith('_') and not m.startswith('__')]
    for method in public_methods[:20]:  # Mostrar solo primeros 20
        print(f"  {method}")
    if len(public_methods) > 20:
        print(f"  ... y {len(public_methods) - 20} más")

if __name__ == "__main__":
    test_engine_exposes_strategy_methods()