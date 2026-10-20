#!/usr/bin/env python3

import sys
sys.path.insert(0, './src')
from utils.contextual_adaptation_engine import ContextualAdaptationEngine, ContextType

engine = ContextualAdaptationEngine()
recs = engine.get_transfer_recommendations(target_context=ContextType.PRODUCTION, max_recommendations=3)
print('RESULT: Recs count:', len(recs))

# Check if knowledge base was updated
if 'transfer_recommendations' in engine.knowledge_base:
    print('RESULT: KB has transfer_recommendations:', len(engine.knowledge_base['transfer_recommendations']))
else:
    print('RESULT: KB missing transfer_recommendations')