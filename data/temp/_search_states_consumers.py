import re, os

root = r"C:\Informatica\PROYECTOS\BACKEND\IA_PYTHON\IA\JARVIS"
# patterns that would indicate consumption of the applications.json boolean states dict
patterns = [
    re.compile(r'\["states"\]'),
    re.compile(r"\.get\(['\"]states['\"]"),
    re.compile(r'\[["\']open["\']\]'),
    re.compile(r'\[["\']active["\']\]'),
    re.compile(r'\[["\']maximized["\']\]'),
    re.compile(r'\[["\']focused["\']\]'),
    re.compile(r'\.get\(["\']open["\']'),
    re.compile(r'\.get\(["\']active["\']'),
    re.compile(r'\.get\(["\']maximized["\']'),
    re.compile(r'\.get\(["\']focused["\']'),
    re.compile(r'application_states'),
]
hits = []
for dirpath, _, files in os.walk(root):
    # skip venvs, caches, data
    if any(seg in ("venv", "__pycache__", ".venv", "node_modules") for seg in dirpath.replace(root, "").split(os.sep)):
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        path = os.path.join(dirpath, f)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    for p in patterns:
                        if p.search(line):
                            rel = os.path.relpath(path, root)
                            hits.append((rel, i, line.rstrip()))
                            break
        except Exception as e:
            pass

# group by file
from collections import defaultdict
by_file = defaultdict(list)
for rel, i, line in hits:
    by_file[rel].append((i, line))

for rel in sorted(by_file):
    print(f"== {rel} ==")
    for i, line in by_file[rel]:
        print(f"  {i}: {line}")
