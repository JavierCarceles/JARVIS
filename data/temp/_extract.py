p='c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/data/temp/fail1b.txt'
s=open(p,encoding='utf-8',errors='replace').read()
i=s.find('FAILURES')
seg=s[i:i+1500]
out=seg.encode('ascii','backslashreplace').decode('ascii')
open('c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/data/temp/fail1c.txt','w',encoding='ascii').write(out)
print('done')