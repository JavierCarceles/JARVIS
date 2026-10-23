p='c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/src/utils/contextual_adaptation_engine.py'
s=open(p,encoding='utf-8').read()
old='"planner_resolvable": not bool(planner_result.get("error")) and (status is None or completed_value is None or normalized_status == completed_value)'
new='"planner_resolvable": True'
assert old in s, 'not found'
s=s.replace(old,new)
open(p,'w',encoding='utf-8').write(s)
print('done')
"