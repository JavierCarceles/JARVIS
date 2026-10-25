import re

with open('src/utils/architectural_evolution_manager.py', 'r', errors='ignore') as f:
    content = f.read()

classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
print('ALL classes in architectural_evolution_manager.py:')
for c in classes:
    print(f'  {c}')

for term in ['AdaptiveGoalSystem', 'AutoImprovementSystem', 'adaptive_goal', 'auto_improvement']:
    matches = list(re.finditer(term, content))
    if matches:
        print(f'  Found "{term}" {len(matches)} times')
        for m in matches[:2]:
            start = max(0, m.start()-50)
            end = min(len(content), m.end()+50)
            print(f'    ...{content[start:end]}...')
