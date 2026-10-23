p="c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/prompt_mejoraActual.txt"
s=open(p,encoding="utf-8").read()
s=s.replace("CURRENT_WORK_STATUS: PARCIALMENTE IMPLEMENTADA","CURRENT_WORK_STATUS: IMPLEMENTADA")
s=s.replace("LAST_COMPLETED_UNIT: 2.8.11.2.11","LAST_COMPLETED_UNIT: 2.8.11.2.12")
open(p,"w",encoding="utf-8").write(s)
print("done")
EOF