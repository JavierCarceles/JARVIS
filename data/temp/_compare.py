import re

# Read the code file
code_path = r'c:\Informatica\PROYECTOS\BACKEND/IA_PYTHON/IA/JARVIS/src/utils/contextual_adaptation_engine.py'
with open(code_path, encoding='utf-8') as f:
    code_lines = f.readlines()

# Extract all method names (inside classes) and global function names
code_methods = set()
code_globals = set()
code_classes = set()

for i, line in enumerate(code_lines):
    m = re.match(r'^class\s+(\w+)', line)
    if m:
        code_classes.add(m.group(1))
    m2 = re.match(r'^    def\s+(\w+)', line)
    if m2:
        code_methods.add(m2.group(1))
    m3 = re.match(r'^def\s+(\w+)', line)
    if m3:
        code_globals.add(m3.group(1))

# Read the README
with open(r'c:\Informatica\PROYECTOS\BACKEND/IA_PYTHON/IA/JARVIS/README.md', encoding='utf-8') as f:
    readme = f.read()

# Extract the section about contextual_adaptation_engine
header = '#### `src/utils/contextual_adaptation_engine.py`'
start = readme.find(header)
if start == -1:
    print('Could not find README section')
    exit()

# Find the next #### heading after this
end = readme.find('\n#### `', start+1)
if end == -1:
    end = len(readme)
section = readme[start:end]

# Extract all method/function names mentioned with backticks
readme_methods = set()
for m in re.finditer(r'`(\w+)`', section):
    name = m.group(1)
    if name not in ('ContextualAdaptationEngine',):
        readme_methods.add(name)

# Find methods in code that are NOT in README
print('=== METHODS IN CODE BUT NOT IN README ===')
for m in sorted(code_methods - readme_methods):
    print(f'  {m}')

print()
print('=== GLOBAL FUNCTIONS IN CODE BUT NOT IN README ===')
for f in sorted(code_globals - readme_methods):
    print(f'  {f}')

print()
print('=== CLASSES IN CODE BUT NOT IN README ===')
for c in sorted(code_classes - readme_methods):
    print(f'  {c}')

print()
print(f'=== TOTAL code methods: {len(code_methods)}, README mentions: {len(readme_methods & code_methods)}')
print(f'=== TOTAL code globals: {len(code_globals)}')
print(f'=== TOTAL code classes: {len(code_classes)}')

# Also check line count
print()
print(f'=== README says line count: checking...')
# Find line count in the section
for line in section.split('\n'):
    if 'lineas' in line or 'líneas' in line or 'lineas' in line.lower():
        print(f'  README line mentions: {line.strip()}')
