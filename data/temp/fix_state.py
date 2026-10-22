p='prompt_mejoraActual.txt'
s=open(p,encoding='utf-8').read()
old='CURRENT_WORK_UNIT: 2.8.8.9.8.3\nCURRENT_WORK_STATUS: IMPLEMENTADA\nLAST_COMPLETED_UNIT: 2.8.8.9.8.3'
new='CURRENT_WORK_UNIT: 2.8.8.9.8.4\nCURRENT_WORK_STATUS: PENDIENTE\nLAST_COMPLETED_UNIT: 2.8.8.9.8.3'
assert old in s, 'pattern not found'
s=s.replace(old,new)
open(p,'w',encoding='utf-8').write(s)
print('done')
