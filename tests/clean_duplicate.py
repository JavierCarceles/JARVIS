#!/usr/bin/env python3

import re

# Leer el archivo original
with open('c:\\Informatica\\PROYECTOS\\BACKEND\\IA_PYTHON\\IA\\JARVIS\\src\\utils\\contextual_adaptation_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Encontrar y eliminar la segunda implementación incorrecta de get_transfer_recommendations
# Buscar desde "def get_transfer_recommendations" hasta el siguiente método o final de clase

# Patrón para encontrar la segunda implementación
pattern = r'(    def get_transfer_recommendations\(self, target_context: ContextType,\n                                    max_recommendations: int = 5\) -> List\[Dict\[str, Any\]\]:.*?return \[\])'

# Reemplazar con vacío (eliminar la implementación)
content_cleaned = re.sub(pattern, '', content, flags=re.DOTALL)

# Escribir el archivo corregido
with open('c:\\Informatica\\PROYECTOS\\BACKEND\\IA_PYTHON\\IA\\JARVIS\\src\\utils\\contextual_adaptation_engine_cleaned.py', 'w', encoding='utf-8') as f:
    f.write(content_cleaned)

print("Archivo limpiado y guardado como contextual_adaptation_engine_cleaned.py")