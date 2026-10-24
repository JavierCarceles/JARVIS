import os, json, sys, tempfile
sys.path.insert(0, r"c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS")
from src.utils.contextual_adaptation_engine import ContextualAdaptationEngine

d = tempfile.mkdtemp()
cfg = {'data_dir': d, 'rules_file': 'ctx_rules.json', 'knowledge_base_file': 'ctx_kb.json', 
       'goal_adaptation_feedback_file': 'fb.json', 'goal_adaptation_learning_results_file': 'lr.json'}
eng = ContextualAdaptationEngine(config=cfg)
r = eng.save_knowledge_base()
print('save:', r)
p = os.path.join(d, 'ctx_kb.json')
print('exists:', os.path.exists(p))
with open(p) as f:
    data = json.load(f)
print('payload_keys:', list(data.keys()))
eng2 = ContextualAdaptationEngine(config=cfg)
r2 = eng2.load_knowledge_base()
print('load:', r2)
print('kb_type:', type(eng2.knowledge_base).__name__)
print('len_kb:', len(eng2.knowledge_base) if isinstance(eng2.knowledge_base, dict) else None)
