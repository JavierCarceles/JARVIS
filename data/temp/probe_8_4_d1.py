import io, json, os, sys, tempfile, logging, traceback

_SANDBOX = tempfile.mkdtemp(prefix="jarvis_8_4_d1_")
for _sub in ("data", "models", "logs", "config"):
    os.makedirs(os.path.join(_SANDBOX, _sub), exist_ok=True)
os.chdir(_SANDBOX)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))
logging.disable(logging.CRITICAL)

from utils.contextual_adaptation_engine import ContextualAdaptationEngine

# 1) ¿Que exception lanza _recuperar_grupos_de_base con default lista?
tmp = tempfile.mkdtemp(); data_dir = os.path.join(tmp, "data"); os.makedirs(data_dir)
json.dump({"version": "2.0", "data": {"learning_results": {"no": "es lista"}}},
          open(os.path.join(data_dir, "contextual_knowledge_base.json"), "w", encoding="utf-8"))
m = ContextualAdaptationEngine(data_dir=data_dir)
try:
    m._recuperar_grupos_de_base("learning_results", {"no": "es lista"})
    print("D1: sin excepcion")
except Exception as exc:
    print("D1: EXCEPCION ->", type(exc).__name__, exc)
    print("   traceback:")
    for line in traceback.format_exc().splitlines()[-6:]:
        print("   ", line)

# 2) ¿Que escribe _save_goal_adaptation_feedback y cuando se llama?
import re
src = io.open(os.path.join(_ROOT, "src", "utils", "contextual_adaptation_engine.py"), encoding="utf-8").read()
for i, l in enumerate(src.split("\n"), 1):
    if "_save_goal_adaptation_feedback" in l or "_save_goal_adaptation_learning_results" in l or "save_all_data" in l:
        print("%5d: %s" % (i, l.strip()[:150]))
