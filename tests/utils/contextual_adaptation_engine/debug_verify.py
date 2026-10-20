#!/usr/bin/env python3

import sys
import os

# Forzar recarga limpia
if 'utils.contextual_adaptation_engine' in sys.modules:
    del sys.modules['utils.contextual_adaptation_engine']
if 'utils' in sys.modules:
    del sys.modules['utils']

# Añadir el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

# Verificar si el método existe
engine = ContextualAdaptationEngine()

print("=== Verificando metodos ===")

# Buscar metodos que contengan "knowledge"
knowledge_methods = [m for m in dir(engine) if 'knowledge' in m.lower() and not m.startswith('__')]
print("Metodos con 'knowledge':", knowledge_methods)

# Buscar metodos que contengan "available"
available_methods = [m for m in dir(engine) if 'available' in m.lower() and not m.startswith('__')]
print("Metodos con 'available':", available_methods)

# Buscar metodos que contengan "type"
type_methods = [m for m in dir(engine) if 'type' in m.lower() and not m.startswith('__')]
print("Metodos con 'type':", type_methods)

# Verificar especificamente _get_available_knowledge_types
if hasattr(engine, '_get_available_knowledge_types'):
    print("EL METODO EXISTE")
else:
    print("EL METODO NO EXISTE")
    
# Intentar obtener el metodo por nombre
method_name = '_get_available_knowledge_types'
if method_name in dir(engine):
    print(f"{method_name} esta en dir()")
else:
    print(f"{method_name} NO esta en dir()")

# Mostrar todos los metodos del objeto que contengan "get"
get_methods = [m for m in dir(engine) if m.startswith('_get_') and not m.startswith('__')]
print("\nTodos los metodos _get_:", get_methods)