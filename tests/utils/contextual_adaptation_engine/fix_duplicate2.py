#!/usr/bin/env python3

# Leer el archivo original
with open('c:\\Informatica\\PROYECTOS\\BACKEND\\IA_PYTHON\\IA\\JARVIS\\src\\utils\\contextual_adaptation_engine.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Encontrar la segunda implementación incorrecta (la que comienza en línea 4765)
start_line = None
end_line = None

for i, line in enumerate(lines):
    if 'def get_transfer_recommendations(self, target_context: ContextType,' in line and 'max_recommendations: int = 5)' in lines[i+1]:
        start_line = i
        # Encontrar el final de esta implementación
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == '' and j + 1 < len(lines) and lines[j+1].startswith('    def ') and not lines[j+1].startswith('    def get_transfer_recommendations'):
                end_line = j
                break
            elif j + 1 == len(lines):
                end_line = j
                break
        break

if start_line is not None and end_line is not None:
    print(f"Eliminando implementación incorrecta desde línea {start_line+1} hasta {end_line+1}")
    
    # Eliminar las líneas de la implementación incorrecta
    new_lines = lines[:start_line] + lines[end_line+1:]
    
    # Escribir el archivo corregido
    with open('c:\\Informatica\\PROYECTOS\\BACKEND\\IA_PYTHON\\IA\\JARVIS\\src\\utils\\contextual_adaptation_engine.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("Archivo corregido exitosamente")
else:
    print("No se encontró la implementación incorrecta para eliminar")