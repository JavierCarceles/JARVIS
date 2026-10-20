import io

P = 'prompt_mejoraActual.txt'
d = open(P, 'r', encoding='utf-8', newline='').read()
L = d.split('\r\n')

print('=== REGISTRO PREVIO 2.8.8.9.4.2 (L3224-3254) ===')
for i in range(3223, 3254):
    print(i + 1, L[i].encode('ascii', 'replace').decode())

print()
print('=== CONTADORES ===')
print('NO tocar adaptation_strategies :', d.count('- NO tocar `adaptation_strategies`'))
print('header 2.8.8.9.4.3            :', d.count('2.8.8.9.4.3 \u2014 IMPLEMENTAR GUARDADO DE PATRONES'))
print('SIGUIENTE UNIDAD: 2.8.8.9.4.3 :', d.count('SIGUIENTE UNIDAD: 2.8.8.9.4.3'))
print('index 2.8.8.9.4.2              :', d.count('### REGISTRO DE UNIDAD: 2.8.8.9.4.2'))
print('index 2.8.8.9.4.3              :', d.count('### REGISTRO DE UNIDAD: 2.8.8.9.4.3'))
print()
print('=== TEST FILE REAL PATH ===')
import os
for root, dirs, files in os.walk('tests'):
    for f in files:
        if 'goal_adaptation_pattern_persistence' in f:
            print(os.path.join(root, f))
