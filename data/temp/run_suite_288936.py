# -*- coding: utf-8 -*-
"""Ejecuta pytest capturando la salida en UTF-8 y lista FAILED/ERROR."""
import subprocess
import sys
import io
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

cmd = [sys.executable, '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider',
       '--continue-on-collection-errors', '-rf']
p = subprocess.run(cmd, capture_output=True, cwd='.')
out = (p.stdout or b'') + (p.stderr or b'')
text = out.decode('utf-8', errors='replace')
open('data/temp/suite_288936.txt', 'w', encoding='utf-8').write(text)
print("EXIT=%d" % p.returncode)

lines = text.splitlines()
print("\n--- RESUMEN ---")
for ln in lines:
    if ln.startswith(('FAILED', 'ERROR')):
        print(ln)
print("\n--- TAIL ---")
for ln in lines[-15:]:
    print(ln)
