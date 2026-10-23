import re, glob, collections
files = glob.glob("tests/utils/contextual_adaptation_engine/test_*.py")
pat = re.compile(r"assert\s+True\b|assert\s+False\b|except[^:]*:\s*pass|pytest\.skip|pytest\.xfail|xfail", re.M)
hits = collections.Counter()
total = 0
for f in files:
    txt = open(f, encoding="utf-8", errors="ignore").read()
    n = len(pat.findall(txt))
    if n:
        hits[f] = n
        total += n
print("files with weak patterns:", len(hits), "total hits", total)
for f,c in sorted(hits.items(), key=lambda x:-x[1])[:40]:
    print(c, f)