import json, os, sys, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from utils.contextual_adaptation_engine import ContextualAdaptationEngine

tmp = tempfile.mkdtemp()
fb = [{"adaptation_id": "a1", "analysis": {}, "timestamp": "t", "status": "processed"}]
lr = [{"adaptation_id": "a1", "learned_patterns": [], "updated_strategies": {}, "convergence_metrics": {}}]
st = {"strategy_001": {"confidence": 0.85, "success_rate": 0.9, "last_updated": "t", "failure_count": 0}}
with open(os.path.join(tmp, "goal_adaptation_feedback.json"), "w", encoding="utf-8") as f:
    json.dump({"goal_adaptation_feedback": fb, "last_updated": "t"}, f)
with open(os.path.join(tmp, "goal_adaptation_learning_results.json"), "w", encoding="utf-8") as f:
    json.dump({"learning_results": lr, "adaptation_strategies": st, "last_updated": "t"}, f)

e = ContextualAdaptationEngine(data_dir=tmp)
print("KEYS:", list(e.knowledge_base.keys()))
print("adaptation_strategies type:", type(e.knowledge_base.get("adaptation_strategies")))
print("adaptation_strategies:", json.dumps(e.knowledge_base.get("adaptation_strategies"), indent=1, default=str))
print("learning_results len:", len(e.knowledge_base.get("learning_results", [])))
print("feedback len:", len(e.knowledge_base.get("goal_adaptation_feedback", [])))
print("--- after load call ---")
e2 = ContextualAdaptationEngine.__new__(ContextualAdaptationEngine)
e2.data_dir = tmp
e2.knowledge_base = {"goal_adaptation_feedback": [], "learning_results": [], "adaptation_strategies": {}}
e2.logger = e.logger
e2.adaptation_history = []
e2._load_goal_adaptation_learning_results()
print("after manual load:", json.dumps(e2.knowledge_base["adaptation_strategies"], indent=1, default=str))
shutil.rmtree(tmp, ignore_errors=True)
