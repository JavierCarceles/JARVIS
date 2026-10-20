# -*- coding: utf-8 -*-
"""Compara ficheros de HEAD con el working tree sin pasar por redireccion de PowerShell."""
import subprocess
import sys
import re
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def head(path):
    p = subprocess.run(['git', 'show', 'HEAD:' + path], capture_output=True)
    if p.returncode != 0:
        return None
    return p.stdout.decode('utf-8', errors='replace')


def work(path):
    if not os.path.exists(path):
        return None
    return open(path, encoding='utf-8', errors='replace').read()


targets = [
    'src/utils/contextual_adaptation_engine.py',
    'src/utils/adaptive_learning_engine.py',
    'tests/test_cross_context_confidence_feedback.py',
    'tests/test_cross_context_knowledge_transfer.py',
    'tests/test_goal_adaptation_learning_loop.py',
    'tests/test_goal_adaptation_proposal.py',
    'tests/test_goal_adaptation_representation.py',
    'tests/test_2_8_5_7_recommendations.py',
    'tests/test_context_compatibility.py',
    'tests/test_evolutionary_strategy_optimizer.py',
]

for t in targets:
    h = head(t)
    w = work(t)
    if h is None:
        print("%-58s HEAD=ausente  WORK=%s" % (t, 'si' if w else 'no'))
        continue
    if w is None:
        print("%-58s HEAD=si  WORK=ausente" % t)
        continue
    print("%-58s HEAD=%6d WORK=%6d  %s" % (t, len(h), len(w), 'IGUAL' if h == w else 'DIFIERE'))

print("\n=== Metodos en HEAD engine (transfer/confidence/feedback/compatib) ===")
h = head('src/utils/contextual_adaptation_engine.py')
if h:
    for m in re.finditer(r'\n[ \t]*def (\w*(?:transfer|confidence|feedback|compatib)\w*)\s*\(([^)]*)\)', h):
        print("   def %s(%s)" % (m.group(1), ' '.join(m.group(2).split())[:90]))
