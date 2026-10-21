import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from utils.contextual_adaptation_engine import ContextualAdaptationEngine
SENT = "SENTINELA_X"
REGLA = {"rule_id": "ok1", "name": "regla sana", "description": "d", "condition_pattern": "c",
    "adaptation_actions": ["a"], "context_triggers": ["production"], "confidence_threshold": 0.7,
    "priority": 1, "enabled": True, "success_rate": 0.5, "execution_count": 3,
    "last_execution": "2024-01-01T00:00:00", "adaptation_score": 0.4, "constraints": [],
    "metadata": {}, "deadline": None}
tmp = tempfile.mkdtemp()
dd = os.path.join(tmp, "data"); os.makedirs(dd)
fila = dict(REGLA, rule_id="bad1", priority=SENT)
payload = {"version":"2.0","last_updated":"x","total_rules":2,"rules":[dict(REGLA), fila]}
with open(os.path.join(dd, "contextual_adaptation_rules.json"), "w", encoding="utf-8") as h:
    json.dump(payload, h)
m = ContextualAdaptationEngine(data_dir=dd)
print("ids:", list(m.adaptation_rules))
r = m.adaptation_rules.get("bad1")
print("bad1:", r.to_dict() if r else None)
print("dev:", m._desviaciones_de_regla(fila))
print("dev_estrictas:", m._desviaciones_estrictas_de_regla(fila))
print("campos:", m._campos_de_formato("adaptation_rules"))
