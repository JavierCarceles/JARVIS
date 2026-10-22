import io, re, sys

p = 'src/utils/contextual_adaptation_engine.py'
lines = io.open(p, encoding='utf-8').read().split('\n')
pat = re.compile(r'"(goal_adaptation_feedback|goal_adaptation_learning_results|knowledge_base)":\s*\{')
for i, l in enumerate(lines, 1):
    if pat.search(l):
        print(i, l.strip())
