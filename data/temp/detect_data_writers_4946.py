# -*- coding: utf-8 -*-
"""Detecta que ficheros de test ESCRIBEN en `data/` de produccion."""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data')


def snapshot():
    out = {}
    for name in sorted(os.listdir(DATA)):
        path = os.path.join(DATA, name)
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as handle:
            out[name] = hashlib.sha256(handle.read()).hexdigest()
    return out


def test_files():
    files = []
    for base, dirs, names in os.walk(os.path.join(ROOT, 'tests')):
        dirs[:] = [d for d in dirs if d not in ('__pycache__',)]
        for name in sorted(names):
            if name.startswith('test_') and name.endswith('.py'):
                files.append(os.path.relpath(os.path.join(base, name), ROOT))
    return sorted(files)


def main():
    offenders = []
    for rel in test_files():
        before = snapshot()
        subprocess.run([sys.executable, '-m', 'pytest', rel, '-q', '-p', 'no:cacheprovider',
                        '--continue-on-collection-errors'],
                       cwd=ROOT, capture_output=True)
        after = snapshot()
        touched = [n for n in before if before.get(n) != after.get(n)]
        added = [n for n in after if n not in before]
        if touched or added:
            offenders.append((rel, touched + added))
            print('WRITE -> %s : %s' % (rel, touched + added))
            sys.stdout.flush()
    print('\n=== RESUMEN: %d ficheros de test escriben en data/ ===' % len(offenders))
    for rel, files in offenders:
        print('  %s -> %s' % (rel, files))


if __name__ == '__main__':
    main()
