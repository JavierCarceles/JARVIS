path='c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/prompt_mejoraActual.txt'
s=open(path,encoding='utf-8').read()
old='2.8.11.9.9 Corregir la identidad no determinista de pattern_id (basada en time.time()) que impide la recuperacion exacta de patrones tras reinicio, y reejecutar los 3 tests afectados en test_goal_adaptation_pattern_restart_verification.py.'
new='2.8.11.9.9 Corregir los defectos del motor detectados por tests bien disenados (incluida la identidad no determinista de pattern_id basada en time.time()), sin debilitar tests, y reejecutar los tests afectados.'
assert old in s
s=s.replace(old,new)
open(path,'w',encoding='utf-8').write(s)
print('done')