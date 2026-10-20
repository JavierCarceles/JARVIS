#!/usr/bin/env python3
import sys

with open('./src/utils/contextual_adaptation_engine.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

current_class = None
class_stack = []
results = []
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    indent = len(line) - len(line.lstrip())
    
    if stripped.startswith('class '):
        class_stack = [(indent, stripped)]
        current_class = stripped
        results.append(f'Line {i}: {stripped} (indent={indent})')
    elif stripped.startswith('def get_transfer_recommendations'):
        results.append(f'  Line {i}: {stripped} (indent={indent})')
        results.append(f'  Class stack: {class_stack}')
    elif stripped.startswith('def _calculate_transfer_potential'):
        results.append(f'  Line {i}: {stripped} (indent={indent})')
        results.append(f'  Class stack: {class_stack}')
    elif stripped.startswith('def _get_available_knowledge_types'):
        results.append(f'  Line {i}: {stripped} (indent={indent})')
        results.append(f'  Class stack: {class_stack}')

# Write results to file
with open('debug_classes_output.txt', 'w', encoding='utf-8') as f:
    for line in results:
        f.write(line + '\n')