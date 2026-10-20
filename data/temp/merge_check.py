import ast, os, sys

RB = r'C:\$Recycle.Bin\S-1-5-21-319373259-2107261026-2196469781-1001'
orig_path = os.path.join(RB, '$RA2X36B.py')
cur_path = r'data\temp\cae_backup.py'

orig = open(orig_path, encoding='utf-8', errors='replace').read()
cur = open(cur_path, encoding='utf-8', errors='replace').read()


def eng(src):
    t = ast.parse(src)
    for n in t.body:
        if isinstance(n, ast.ClassDef) and n.name == 'ContextualAdaptationEngine':
            return {m.name: m for m in n.body if isinstance(m, ast.FunctionDef)}
    return {}


O, C = eng(orig), eng(cur)
print('metodos ORIGINAL:', len(O), '| metodos HOY:', len(C))
print()
print('COLISIONES (nombre en ambos):')
for k in sorted(set(O) & set(C)):
    print('   %-40s orig_line=%s hoy_line=%s' % (k, O[k].lineno, C[k].lineno))
print()
print('SOLO EN HOY (a re-añadir):')
for k in sorted(set(C) - set(O)):
    print('   %-40s line=%s' % (k, C[k].lineno))
print()
print('CLASES en original:', [n.name for n in ast.parse(orig).body if isinstance(n, ast.ClassDef)])
print('CLASES en hoy     :', [n.name for n in ast.parse(cur).body if isinstance(n, ast.ClassDef)])
print()
print('knowledge_base en ORIGINAL:')
for i, l in enumerate(orig.splitlines(), 1):
    if 'knowledge_base' in l and ('=' in l):
        print('   %5d: %s' % (i, l.strip()))
print()
print('knowledge_base en HOY:')
for i, l in enumerate(cur.splitlines(), 1):
    if 'knowledge_base' in l and ('=' in l):
        print('   %5d: %s' % (i, l.strip()))
