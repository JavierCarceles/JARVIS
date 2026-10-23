p='c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/prompt_mejoraActual.txt'
s=open(p,encoding='utf-8').read()
old="ESTADO FINAL: 2.8.11.2.12 - PARCIALMENTE IMPLEMENTADA"
new=("ESTADO FINAL: 2.8.11.2.12 - IMPLEMENTADA\n"
     "RESULTADO EJECUCION COMPLETA: 10 failed, 719 passed, 2 warnings, 41 subtests passed in 268.25s.\n"
     "FALLOS: test_goal_adaptation_learned_strategy_persistence (1), test_goal_adaptation_pattern_persistence (1), test_goal_adaptation_pattern_restart_verification (2), test_goal_adaptation_persistence_real (3), test_goal_adaptation_proposal (3).")
assert old in s
s=s.replace(old,new,1)
open(p,'w',encoding='utf-8').write(s)
print("done")
