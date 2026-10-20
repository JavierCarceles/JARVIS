# -*- coding: utf-8 -*-
"""Recolecta la suite y reporta errores de coleccion sin ruido de logs."""
import subprocess
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

cmd = [sys.executable, '-m', 'pytest', 'tests', '--collect-only', '-q',
       '-p', 'no:cacheprovider', '--continue-on-collection-errors']
p = subprocess.run(cmd, capture_output=True, cwd='.', env={**os.environ, 'PYTHONWARNINGS': 'ignore'})
text = ((p.stdout or b'') + (p.stderr or b'')).decode('utf-8', errors='replace')
open('data/temp/collect_288936.txt', 'w', encoding='utf-8').write(text)
print("EXIT=%d" % p.returncode)
for ln in text.splitlines():
    if ln.startswith('ERROR') or ln.startswith('E   '):
        print(ln[:220])
