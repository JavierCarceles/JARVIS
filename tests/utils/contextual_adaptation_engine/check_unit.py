import sys, os, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))
from utils.contextual_adaptation_engine import ContextualAdaptationEngine
e = ContextualAdaptationEngine()
# Check persistence methods
for m in ['_save_adaptation_rules','_load_adaptation_rules','save_knowledge_base','load_knowledge_base','_save_knowledge_base','_load_knowledge_base','_persist_goal_adaptation','persist_adaptation']:
    print(m, hasattr(e, m))
print('--- kb keys ---')
print(list(e.knowledge_base.keys()))
print('--- config kb file ---')
print(e.config.get('knowledge_base_file'))
# Try the 2.8.8.8 test
import traceback
try:
    r = e._capture_goal_adaptation_feedback({
        "adaptation_id":"t1","original_goal_id":"g1","adapted_goal_id":"g2",
        "adaptation_context":{"expected_metrics":{"response_time":2.0,"accuracy":0.9}},
        "execution_result":{"success":True,"performance_metrics":{"response_time":1.5,"accuracy":0.95}},
        "verification_result":{"verified":True,"impact_score":0.8}
    })
    print('feedback capture OK:', r.get('success'))
except Exception as ex:
    print('feedback capture ERR:', ex)
try:
    r = e._execute_goal_adaptation_learning_loop({})
    print('learning loop OK:', r.get('success'))
except Exception as ex:
    print('learning loop ERR:', type(ex).__name__, ex)