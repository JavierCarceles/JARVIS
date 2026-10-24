import os
import re

# Count test functions per file
for root, dirs, files in os.walk('tests'):
    if 'venv' in root:
        continue
    for f in files:
        if f.endswith('.py') and f.startswith('test'):
            path = os.path.join(root, f)
            try:
                with open(path, encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
                tests = re.findall(r'^\s*def (test_[a-zA-Z0-9_]+)\s*\(', content, re.M)
                if tests:
                    print(f'{path}: {len(tests)} tests -> {tests[0]}')
            except Exception as e:
                print(f'ERR {path}: {e}')
