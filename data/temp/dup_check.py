# -*- coding: utf-8 -*-
import io, re

lines = io.open(r'src/utils/contextual_adaptation_engine.py', encoding='utf-8', errors='replace').read().split('\n')

for name in ['get_transfer_recommendations', 'get_transfer_confidence',
             'register_transfer_feedback', 'evaluate_transfer_result']:
    print('###', name)
    for i, t in enumerate(lines):
        if re.match(r'^\s*def %s\b' % name, t):
            seg = '\n'.join(lines[i:i + 150])
            keys = sorted(set(re.findall(r'"([a-z_]+)"\s*:', seg)))
            print('   def en linea %d -> claves: %s' % (i + 1, ', '.join(keys[:24])))
    print()
