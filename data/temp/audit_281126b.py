import re, glob, collections
files = glob.glob("tests/utils/contextual_adaptation_engine/test_*.py")
patterns = {
 "skip_mark": re.compile(r"@pytest\.mark\.skip"),
 "xfail_mark": re.compile(r"@pytest\.mark\.xfail"),
 "bare_except": re.compile(r"except\s*:"),
 "except_pass": re.compile(r"except[^:]*:\s*\n\s*pass"),
 "assert_true": re.compile(r"assert\s+True"),
 "assert_not_none_only": re.compile(r"assert\s+\w+\s+is\s+not\s+None\s*$", re.M),
 "return_true": re.compile(r"return\s+True"),
}
agg = collections.Counter()
for name,pat in patterns.items():
    n=0
    for f in files:
        txt=open(f,encoding="utf-8",errors="ignore").read()
        n+=len(pat.findall(txt))
    agg[name]=n
    print(name, n)
print("TOTAL FILES:", len(files))