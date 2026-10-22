import io, re

p = 'src/utils/contextual_adaptation_engine.py'
src = io.open(p, encoding='utf-8').read()
lines = src.split('\n')
pats = {
    'condition_pattern': r'condition_pattern',
    'learning_results append': r'learning_results',
    'adaptation_id': r'adaptation_id',
}
for key, pat in pats.items():
    print('#### ' + key)
    rx = re.compile(pat)
    for i, l in enumerate(lines, 1):
        if rx.search(l):
            print('  %5d: %s' % (i, l.strip()[:170]))
    print()
