"""Revert and properly fix error logging in storage.py (3.2.3.3)."""
import re

filepath = r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS\src\memory\storage.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Step 1: Revert all the incorrect replacements back to original
pattern = r'logger\._print_log\("error", f"Error en [^:]+: \{e\}", "storage\.py", "[^"]+", \d+\)'
content = re.sub(pattern, 'logger._print_log("info", "Procesando solicitud", "storage.py", "method", 393)', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify reversion
remaining = len(re.findall(pattern, content))
original_count = content.count('logger._print_log("info", "Procesando solicitud", "storage.py", "method", 393)')
print(f'Reverted. Remaining incorrect patterns: {remaining}, Restored original count: {original_count}')
