import re, glob
files = glob.glob("tests/utils/contextual_adaptation_engine/test_*.py")
pat = re.compile(r"assert\s+\w+\s+is\s+not\s+None\s*$", re.M)
for f in files:
    for i,line in enumerate(open(f,encoding="utf-8",errors="ignore"),1):
        if pat.search(line):
            print(f, i, line.strip())
print("---return_true---")
pat2 = re.compile(r"return\s+True")
for f in files:
    for i,line in enumerate(open(f,encoding="utf-8",errors="ignore"),1):
        if pat2.search(line):
            print(f, i, line.strip())