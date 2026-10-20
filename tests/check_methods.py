#!/usr/bin/env python3
import sys
sys.path.insert(0, './src')
from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType
engine = ContextualAdaptationEngine()

methods = [
    '_estimate_transfer_efficiency',
    '_generate_transfer_reasoning',
    '_calculate_transfer_priority',
]
for m in methods:
    if hasattr(engine, m):
        print(f'{m}: EXISTS')
    else:
        print(f'{m}: MISSING')

# Also read the output to a file to avoid encoding issues
import sys
original_stdout = sys.stdout
with open('check_methods_out.txt', 'w', encoding='utf-8') as f:
    for m in methods:
        if hasattr(engine, m):
            f.write(f'{m}: EXISTS\n')
        else:
            f.write(f'{m}: MISSING\n')

# Also print to stdout using ASCII only
for m in methods:
    status = 'EXISTS' if hasattr(engine, m) else 'MISSING'
    print(f'{m}: {status}')