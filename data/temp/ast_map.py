import ast, collections
p = r"src\utils\contextual_adaptation_engine.py"
src = open(p, encoding="utf-8").read()
tree = ast.parse(src)
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        print("CLASS", node.name, node.lineno, "-", node.end_lineno)
        d = collections.defaultdict(list)
        for m in node.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                d[m.name].append((m.lineno, m.end_lineno, len(m.args.args)))
        for name, occ in d.items():
            if len(occ) > 1:
                print("  DUP", name, occ)
