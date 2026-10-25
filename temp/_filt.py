import re, sys
path = sys.argv[1]
for line in open(path, encoding="utf-8", errors="replace"):
    if re.match(r"^(TOTAL|PROBLEMAS)", line) or "det=" in line:
        print(line.rstrip())
