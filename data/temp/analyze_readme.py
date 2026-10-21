"""Analisis del README frente al arbol real de src/."""
import ast
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SRC = ROOT / "src"

lines = README.read_text(encoding="utf-8").splitlines()

# --- entradas del README ---
entries = []
for i, l in enumerate(lines):
    m = re.match(r"^####\s+`([^`]+)`", l)
    if m:
        entries.append((i + 1, m.group(1), l))

counts = Counter(p for _, p, _ in entries)
src_files = sorted(
    p.relative_to(ROOT).as_posix() for p in SRC.rglob("*.py")
)

print("=== ENTRADAS README ===")
print("total entradas ####:", len(entries))
print("ficheros unicos en README:", len(counts))
print("ficheros .py en src/:", len(src_files))
print()
print("--- DUPLICADOS en README ---")
for p, c in sorted(counts.items()):
    if c > 1:
        nums = [n for n, q, _ in entries if q == p]
        print(f"  {c}x  {p}  lineas {nums}")
print()
print("--- src/ NO documentado en README ---")
for p in src_files:
    if p not in counts:
        print("  ", p)
print()
print("--- entradas README que NO son de src/ ---")
for p in counts:
    if not p.startswith("src/") and p != "main.py":
        print("  ", p)

# --- docstrings disponibles ---
print()
print("=== DOCSTRINGS EN src/ ===")
tot_cls = tot_cls_doc = tot_meth = tot_meth_doc = 0
for p in src_files:
    tree = ast.parse((ROOT / p).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            tot_cls += 1
            if ast.get_docstring(node):
                tot_cls_doc += 1
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    tot_meth += 1
                    if ast.get_docstring(sub):
                        tot_meth_doc += 1
print(f"clases: {tot_cls} (con docstring {tot_cls_doc})")
print(f"metodos de clase: {tot_meth} (con docstring {tot_meth_doc})")
