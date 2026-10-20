# -*- coding: utf-8 -*-
"""Diff HEAD vs working tree del engine contextual."""
import subprocess
import sys
import os
import difflib

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

p = subprocess.run(['git', 'show', 'HEAD:src/utils/contextual_adaptation_engine.py'], capture_output=True)
h = p.stdout.decode('utf-8', errors='replace').splitlines()
w = open('src/utils/contextual_adaptation_engine.py', encoding='utf-8', errors='replace').read().splitlines()

d = list(difflib.unified_diff(h, w, 'HEAD', 'WORK', lineterm='', n=1))
print("LINEAS DIFF:", len(d))
for ln in d:
    print(ln[:200])
