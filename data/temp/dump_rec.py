import sys, json
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from utils.contextual_adaptation_engine import ContextualAdaptationEngine
m = ContextualAdaptationEngine(data_dir="data/temp/_dump_dir")
r = m.recoverable_data()
print("TOP KEYS:", list(r.keys()))
print("\n-- levels --"); print(json.dumps(r.get("levels"), indent=1, ensure_ascii=False))
print("\n-- policies --"); print(json.dumps(r.get("policies"), indent=1, ensure_ascii=False))
print("\n-- field_defaults --"); print(json.dumps(r.get("field_defaults"), indent=1, ensure_ascii=False))
print("\n-- conservative_defaults --"); print(r.get("conservative_defaults"))
print("\n-- independence_rule --"); print(r.get("independence_rule"))
print("\n-- reconciliation --"); print(json.dumps(r.get("reconciliation"), indent=1, ensure_ascii=False))
for clave, spec in r["files"].items():
    print(f"\n=== FILE {clave} ===")
    for cid, clase in spec["classes"].items():
        print(json.dumps(clase, ensure_ascii=False))
