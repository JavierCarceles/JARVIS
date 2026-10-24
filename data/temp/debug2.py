#!/usr/bin/env python3
"""Reproduce the exact test _learn flow (double learning loop call)."""
import sys, os, tempfile, json, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

tmp = tempfile.mkdtemp()
engine = ContextualAdaptationEngine(data_dir=tmp)

def _feedback(adaptation_id, success=True, verified=True, impact=0.8,
              goal_type='navigation', context_type=ContextType.PRODUCTION.value,
              response_time=1.2, accuracy=0.97):
    return {
        'adaptation_id': adaptation_id,
        'original_goal_id': f'goal_original_{adaptation_id}',
        'adapted_goal_id': f'goal_adapted_{adaptation_id}',
        'adaptation_context': {
            'goal_type': goal_type, 'context_type': context_type,
            'system_resources': {'cpu': 0.5, 'memory': 0.3},
            'expected_metrics': {'response_time': 2.0, 'accuracy': 0.95}},
        'execution_result': {'success': success,
            'performance_metrics': {'response_time': response_time, 'accuracy': accuracy}},
        'verification_result': {'verified': verified, 'impact_score': impact},
    }

produced = []
for index in range(1, 4):
    data = _feedback(f'obs_{index}')
    fr = engine._capture_goal_adaptation_feedback(data)
    lr = engine._execute_goal_adaptation_learning_loop(fr)
    produced.extend(lr['learned_patterns'])

print('PRODUCED (explicit call only):')
for p in produced: print(' ', p['pattern_id'], p['timestamp'])

path = os.path.join(tmp, 'goal_adaptation_learning_results.json')
with open(path) as f:
    persisted = json.load(f)
allp = [p for row in persisted.get('learning_results', []) for p in (row.get('learned_patterns') or [])]
print('PERSISTED total entries:', len(allp))
for p in allp: print(' ', p.get('pattern_id'), p.get('timestamp'))

restarted = ContextualAdaptationEngine(data_dir=tmp)
rec = [p for row in restarted.knowledge_base.get('learning_results', []) for p in (row.get('learned_patterns') or [])]
print('RECOVERED total entries:', len(rec))
for p in rec: print(' ', p.get('pattern_id'), p.get('timestamp'))

by_id = {p['pattern_id']: p for p in rec}
print('by_id keys:', list(by_id.keys()))
for original in produced:
    pat = by_id.get(original['pattern_id'])
    print('compare produced ts', original['timestamp'], 'vs recovered', pat['timestamp'] if pat else None)