path='c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/prompt_mejoraActual.txt'
s=open(path,encoding='utf-8').read()
old='2.8.11.9.8 Marcar 2.8.11 como IMPLEMENTADA solo cuando todas sus hojas esten completadas y verificadas; no ocultar fallos ni convertir tests fallidos en PASSED por cambios de aserciones, mocks'
new=old+'\n2.8.11.9.9 Corregir la identidad no determinista de pattern_id (basada en time.time()) que impide la recuperacion exacta de patrones tras reinicio, y reejecutar los 3 tests afectados en test_goal_adaptation_pattern_restart_verification.py.'
assert old in s
s=s.replace(old,new)
open(path,'w',encoding='utf-8').write(s)
print('done')