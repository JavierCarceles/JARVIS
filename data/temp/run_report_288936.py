# -*- coding: utf-8 -*-
"""Ejecuta la suite con el plugin de informe y lista los fallos con su error."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

REPORT = os.path.abspath('data/temp/report_288936.json')
cmd = [sys.executable, '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider',
       '-p', 'jarvis_report_plugin', '--tb=no', '-q']
env = {**os.environ, 'PYTHONWARNINGS': 'ignore',
       'PYTHONPATH': os.path.abspath('data/temp'), 'JARVIS_REPORT_JSON': REPORT}
p = subprocess.run(cmd, capture_output=True, cwd='.', env=env)
text = ((p.stdout or b'') + (p.stderr or b'')).decode('utf-8', errors='replace')
open('data/temp/full_report_run.txt', 'w', encoding='utf-8').write(text)

for ln in text.splitlines():
    if ' passed' in ln or ' failed' in ln:
        print('RESUMEN:', ln.strip()[:160])

if not os.path.exists(REPORT):
    print('SIN INFORME')
    raise SystemExit(1)
data = json.load(open(REPORT, encoding='utf-8'))
fails = {k: v for k, v in data.items() if v['outcome'] == 'failed'}
print('\n--- %d FALLOS ---\n' % len(fails))
for k, v in fails.items():
    print('### %s\n    %s\n' % (k, v['msg'][:260]))
