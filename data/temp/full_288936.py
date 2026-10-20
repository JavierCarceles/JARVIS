# -*- coding: utf-8 -*-
"""Suite completa: ejecuta y extrae el resumen de fallos de forma legible."""
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

OUT = 'data/temp/full_288936.txt'
cmd = [sys.executable, '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider',
       '--tb=line', '-rf']
p = subprocess.run(cmd, capture_output=True, cwd='.',
                   env={**os.environ, 'PYTHONWARNINGS': 'ignore'})
text = ((p.stdout or b'') + (p.stderr or b'')).decode('utf-8', errors='replace')
open(OUT, 'w', encoding='utf-8').write(text)

print("EXIT=%d" % p.returncode)
tail = text.strip().splitlines()[-1] if text.strip() else ''
print("RESUMEN:", tail[:200])

# Extraer lineas FAILED
fails = [ln for ln in text.splitlines() if re.match(r'^(FAILED|ERROR)\s', ln)]
print("\n--- FALLOS (%d) ---" % len(fails))
for ln in fails:
    print(ln[:200])
