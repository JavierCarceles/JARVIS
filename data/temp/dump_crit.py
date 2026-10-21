import re, sys, io
sys.stdout.reconfigure(encoding="utf-8")
src = open(r'src/utils/contextual_adaptation_engine.py', encoding='utf-8').read()
i = src.index('_CORRUPTION_CRITERIA: Dict[str, Any] = {')
blk = src[i:i+14000]
for m in re.finditer(r'"id": "([^"]+)"', blk):
    seg = blk[m.start():m.start()+3000]
    exp = re.search(r'"expected": \[([^\]]*)\]', seg)
    pol = re.search(r'"policy": "([^"]*)"', seg)
    print(m.group(1), '|', (' '.join(exp.group(1).split()) if exp else '?'), '|', (pol.group(1) if pol else '-'))
