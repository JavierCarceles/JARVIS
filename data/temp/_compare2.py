import re

# Read the code file and extract method/function/class names
code_path = r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS/src/utils/contextual_adaptation_engine.py'
with open(code_path, encoding='utf-8') as f:
    code_lines = f.readlines()

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
with open(r'c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS/README.md', encoding='utf-8') as f:
    readme = f.read()

# Extract the section about contextual_adaptation_engine
header = '#### `src/utils/contextual_adaptation_engine.py`'
start = readme.find(header)
if start == -1:
    print('Could not find README section')
    exit()

end = readme.find('\n#### `', start+1)
if end == -1:
    end = len(readme)
section = readme[start:end]

# Better regex: capture word chars right after a backtick, regardless of what follows
backtick_words = set()
for m in re.finditer(r'`([a-zA-Z_]\w*)', section):
    backtick_words.add(m.group(1))

# Filter out non-method words that are common in the README
# (like "ContextualAdaptationEngine", file names, etc.)
# Actually, let's just check directly

# Check specific methods
test_names = ['get_available_strategies', 'generate_strategy_candidates', 'apply_strategy',
              'validate_candidate_strategy', 'evaluate_candidate_strategy', 'select_strategy',
              'compare_strategies', 'knowledge_transaptors', 'get_knowledge_transfer_objects',
              'to_dict', 'no_data_behavior', 'minimum_evidence', 'register_feedback',
              'corruption_criteria', 'recoverable_data', 'total_loss_fallback', 'recovery_report',
              'expected_storage_sections', 'detect_absent_sections', 'detect_corruption',
              'expected_storage_paths', 'detect_absent_storage']
print('=== Checking specific methods ===')
for name in test_names:
    found = name in backtick_words
    print(f'  {name}: {"FOUND" if found else "MISSING"}')

# Find code methods not in README
code_methods_missing = set()
for m in code_methods:
    if m not in backtick_words:
        code_methods_missing.add(m)

code_globals_missing = set()
for f in code_globals:
    if f not in backtick_words:
        code_globals_missing.add(f)

code_classes_missing = set()
for c in code_classes:
    if c not in backtick_words:
        code_classes_missing.add(c)

print()
print('=== ACTUAL MISSING methods (fixed regex) ===')
for m in sorted(code_methods_missing):
    print(f'  {m}')
print(f'Total missing methods: {len(code_methods_missing)}')

print()
print('=== MISSING global functions ===')
for f in sorted(code_globals_missing):
    print(f'  {f}')

print()
print('=== MISSING classes ===')
for c in sorted(code_classes_missing):
    print(f'  {c}')
