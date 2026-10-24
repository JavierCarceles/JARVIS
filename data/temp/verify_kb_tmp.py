import os, json, tempfile, sys
sys.path.insert(0, r"c:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS")
from src.utils.contextual_adaptation_engine import ContextualAdaptationEngine

d = tempfile.mkdtemp()
cfg = {'data_dir': d, 'rules_file': 'ctx_rules.json', 'knowledge_base_file': 'ctx_kb.json', 
       'goal_adaptation_feedback_file': 'fb.json', 'goal_adaptation_learning_results_file': 'lr.json'}
eng = ContextualAdaptationEngine(config=cfg)
ok = eng.save_knowledge_base()
print('save_ok', ok)
p = os.path.join(d, 'ctx_kb.json')
print('exists', os.path.exists(p))
if os.path.exists(p):
    with open(p) as f:
        data = json.load(f)
    print(list(data.keys()))
eng2 = ContextualAdaptationEngine(config=cfg)
ok2 = eng2.load_knowledge_base()
print('load_ok', ok2)
print('kb_has_keys', isinstance(eng2.knowledge_base, dict) and len(eng2.knowledge_base) > 0)
