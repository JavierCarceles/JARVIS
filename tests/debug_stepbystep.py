#!/usr/bin/env python3

import sys
sys.path.insert(0, './src')
from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

engine = ContextualAdaptationEngine()

# Test paso a paso
source_context = ContextType.DEVELOPMENT
target_context = ContextType.PRODUCTION

print('ContextType values:', [c.value for c in ContextType])
print('source:', source_context.value, 'target:', target_context.value)

# Step 1: potential
potential = engine._calculate_transfer_potential(source_context, target_context)
print('Potential:', potential)

# Step 2: compatibility
compatibility = engine._validate_context_compatibility(source_context, target_context)
print('Compatibility:', compatibility)

# Step 3: efficiency
efficiency = engine._get_historical_compatibility(source_context, target_context)
print('Efficiency:', efficiency)

# Step 4: urgency
urgency = engine._calculate_transfer_urgency(target_context, 'success_patterns')
print('Urgency:', urgency)

# Step 5: priority
priority = compatibility * 0.4 + potential * 0.3 + efficiency * 0.2 + urgency * 0.1
print('Priority:', priority)

# Step 6: knowledge types (inline)
knowledge_types = []
for kt in ['success_patterns', 'adaptation_strategies', 'performance_baselines']:
    if kt in engine.knowledge_base:
        data = engine.knowledge_base[kt]
        print(f'  {kt}: in data={source_context.value in data}, value={data.get(source_context.value, "N/A")}')
        if source_context.value in data and data[source_context.value]:
            knowledge_types.append(kt)
print('Knowledge types:', knowledge_types)

# Step 7: reasoning
try:
    reasoning = engine._generate_recommendation_reasoning(source_context, target_context, 'success_patterns', compatibility, priority)
    print('Reasoning OK')
except Exception as e:
    print('Reasoning ERROR:', e)
    import traceback
    traceback.print_exc()

print()
print('Now calling get_transfer_recommendations:')
recs = engine.get_transfer_recommendations(target_context=ContextType.PRODUCTION, max_recommendations=3)
print('Recs count:', len(recs))
if recs:
    for r in recs[:2]:
        print(f"  {r['source_context']} -> {r['target_context']}, priority={r['priority']:.3f}")