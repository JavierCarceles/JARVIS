import re

with open(r'c:\Informatica\PROYECTOS\BACKEND/IA_PYTHON\IA/JARVIS/README.md', encoding='utf-8') as f:
    readme = f.read()

header = '#### `src/utils/contextual_adaptation_engine.py`'
start = readme.find(header)
end = readme.find('\n#### `', start+1)
if end == -1:
    end = len(readme)
section = readme[start:end]

# Extract ALL lines that look like method entries (lines starting with spaces and containing backtick method name)
method_lines = []
for line in section.split('\n'):
    m = re.match(r'^(\s+)- `([a-zA-Z_]\w*)`', line)
    if m:
        method_lines.append((m.group(2), line.strip()))

# Find duplicates
from collections import Counter
names = [name for name, _ in method_lines]
counts = Counter(names)
print("=== DUPLICATED method names in README section ===")
for name, count in counts.most_common():
    if count > 1:
        print(f"  {name}: {count} occurrences")
        for n, line in method_lines:
            if n == name:
                print(f"    -> {line}")

# Check specific methods that might be duplicated
print("\n=== Checking specific methods ===")
for name in ['_execute_single_action', '_set_optimization_interval', '_reduce_data_transfer_real',
             '_calculate_overall_impact', '_calculate_adaptation_confidence', '_record_adaptation_result',
             'record_resource_allocation', '_update_resource_usage_patterns', 'apply_strategy',
             'compare_strategies', 'select_strategy', 'to_dict']:
    found_count = names.count(name)
    if found_count > 1:
        print(f"  DUPLICATE: {name} appears {found_count} times")
    elif found_count == 1:
        print(f"  OK (1): {name}")
    else:
        print(f"  MISSING: {name}")
