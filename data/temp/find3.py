import io

p = 'src/utils/contextual_adaptation_engine.py'
lines = io.open(p, encoding='utf-8').read().split('\n')
for i, l in enumerate(lines, 1):
    if '_valores_por_defecto' in l:
        print('%5d: %s' % (i, l.strip()[:170]))
print('---')
for i in range(2725, 2745):
    print('%5d: %s' % (i, lines[i - 1].strip()[:170]))
