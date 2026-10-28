"""Fix remaining 'Procesando solicitud' error hiding blocks in storage.py (3.2.3.3).

For each occurrence of the generic log pattern inside an except block,
determine the enclosing method/function name by scanning backward for the
nearest 'def' line, then replace with a proper error-level log that includes
the exception.
"""
import re

filepath = r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS\src\memory\storage.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

generic_log = 'logger._print_log("info", "Procesando solicitud", "storage.py", "method", 393)'

def find_enclosing_method(lines, idx):
    """Find the nearest 'def' line before line idx, handling multi-line signatures."""
    for j in range(idx - 1, -1, -1):
        stripped = lines[j].strip()
        if stripped.startswith('def '):
            # Extract method/function name
            m = re.match(r'def\s+(\w+)', stripped)
            if m:
                return m.group(1)
    return 'unknown'

replacements = []

for i, line in enumerate(lines):
    if generic_log not in line:
        continue

    # Check if this is inside an except block
    except_line = None
    for j in range(i - 1, max(i - 6, -1), -1):
        if 'except' in lines[j]:
            except_line = j
            break

    if except_line is None:
        # This might be a success/info log, not in an except block
        # Check if the next line is 'return' to determine context
        # For now, skip these (they're not error-hiding)
        continue

    method_name = find_enclosing_method(lines, i)
    indent = line[:len(line) - len(line.lstrip())]

    new_log = (
        f'{indent}logger._print_log("error", '
        f'f"Error en {method_name}: {{e}}", '
        f'"storage.py", "{method_name}", {i + 1})\n'
    )
    replacements.append((i, line.rstrip(), new_log.rstrip()))

# Also handle non-except blocks that use the generic message
# These are info-level log calls in success paths or cache operations
non_except_replacements = []
for i, line in enumerate(lines):
    if generic_log not in line:
        continue
    # Skip if already in replacements
    if any(r[0] == i for r in replacements):
        continue

    method_name = find_enclosing_method(lines, i)
    indent = line[:len(line) - len(line.lstrip())]

    # These are success/info paths - use a meaningful info message
    new_log = (
        f'{indent}logger._print_log("info", '
        f'f"Operacion completada en {method_name}", '
        f'"storage.py", "{method_name}", {i + 1})\n'
    )
    non_except_replacements.append((i, line.rstrip(), new_log.rstrip()))

# Apply all replacements in reverse order
for idx, old, new in reversed(replacements + non_except_replacements):
    lines[idx] = new + '\n'

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f'Fixed {len(replacements)} except-block error logs (info -> error with exception)')
print(f'Fixed {len(non_except_replacements)} non-except generic logs (info with meaningful message)')
print()
for idx, old, new in replacements:
    print(f'  EXCEPT  Line {idx+1}: {old[:70]}')
    print(f'          -> {new[:90]}')
print()
for idx, old, new in non_except_replacements:
    print(f'  INFO    Line {idx+1}: {old[:70]}')
    print(f'          -> {new[:90]}')
