import os, tempfile, json, sys
sys.path.insert(0,'c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/src')
from utils.contextual_adaptation_engine import ContextualAdaptationEngine
tmp=tempfile.mkdtemp()
data=os.path.join(tmp,'data'); os.makedirs(data)
for f in ['goal_adaptation_feedback.json','goal_adaptation_learning_results.json','contextual_adaptation_rules.json','contextual_knowledge_base.json']:
    with open(os.path.join(data,f),'w') as fh: fh.write('{not json')
m=ContextualAdaptationEngine(data_dir=data)
print('load', m.load_all_data())
snap=m.capture_context_snapshot()
rules=m.analyze_contextual_patterns(snap)
res=m.execute_adaptation(snap, rules)
print('result', res, getattr(res,'success',None))