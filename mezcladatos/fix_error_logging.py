"""Script para corregir el registro de errores en storage.py (3.2.3.3)."""
import re

filepath = r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS\src\memory\storage.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

generic_log = 'logger._print_log("info", "Procesando solicitud", "storage.py", "method", 393)'

replacements = []
current_method = None
current_func = None  # For module-level functions

for i, line in enumerate(lines):
    stripped = line.strip()
    # Track method names (indented def)
    if stripped.startswith('def ') and stripped.endswith(':') and line.startswith('    '):
        m = re.match(r'def (\w+)\(', stripped)
        if m:
            current_method = m.group(1)
    # Track module-level function names
    elif stripped.startswith('def ') and stripped.endswith(':') and not line.startswith(' '):
        m = re.match(r'def (\w+)\(', stripped)
        if m:
            current_func = m.group(1)
            current_method = m.group(1)

    if generic_log in line:
        except_line = None
        for j in range(i - 1, max(i - 5, -1), -1):
            if 'except Exception as e' in lines[j] or 'except Exception' in lines[j]:
                except_line = j
                break

        if except_line is not None:
            indent = line[:len(line) - len(line.lstrip())]
            # Determine which function/method we are in
            func_name = current_method if current_method else 'unknown'
            new_log = (
                f'{indent}logger._print_log("error", '
                f'f"Error en {func_name}: {{e}}", '
                f'"storage.py", "{func_name}", {i + 1})\n'
            )
            replacements.append((i, line.rstrip(), new_log.rstrip()))

# Apply replacements in reverse order
for idx, old_line, new_line in reversed(replacements):
    lines[idx] = new_line + '\n'

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f'Replaced {len(replacements)} occurrences')
for idx, old, new in replacements:
    print(f'  Line {idx + 1}: -> {new[:100]}')
