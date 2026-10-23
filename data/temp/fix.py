p='src/utils/contextual_adaptation_engine.py'
s=open(p,encoding='utf-8').read()
needle='rows.append({"adaptation_id": adaptation_id, "learned_patterns": patterns, "updated_strategies": strategies,'
assert needle in s
replacement='if not any(isinstance(r, dict) and r.get("adaptation_id") == adaptation_id for r in rows):\n            rows.append({"adaptation_id": adaptation_id, "learned_patterns": patterns, "updated_strategies": strategies,'
s=s.replace(needle,replacement,1)
open(p,'w',encoding='utf-8').write(s)
print('done')
