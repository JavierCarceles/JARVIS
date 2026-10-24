path='c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/prompt_mejoraActual.txt'
s=open(path,encoding='utf-8').read()
s=s.replace('tests afectados. o skips.','tests afectados.')
open(path,'w',encoding='utf-8').write(s)
print('done')