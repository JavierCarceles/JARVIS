import ast
p = r"src\utils\contextual_adaptation_engine.py"
src = open(p, encoding="utf-8").read()
tree = ast.parse(src)
cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=="ContextualAdaptationEngine"][0]
for m in cls.body:
    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
        print(f"{m.lineno:6d}-{m.end_lineno:6d}  {m.name}")
