p='prompt_mejoraActual.txt'
s=open(p,encoding='utf-8').read()
s=s.replace('CURRENT_WORK_STATUS: PENDIENTE','CURRENT_WORK_STATUS: IMPLEMENTADA')
s=s.replace('LAST_COMPLETED_UNIT: 2.8.8.9.13.1','LAST_COMPLETED_UNIT: 2.8.8.9.13.2')
open(p,'w',encoding='utf-8').write(s)
print('done')
