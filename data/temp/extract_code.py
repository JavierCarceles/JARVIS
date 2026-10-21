"""Extractor tolerante de clases/metodos/funciones (no requiere codigo valido)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RE_CLASS = re.compile(r"^(\s*)class\s+(\w+)\s*(\(([^)]*)\))?\s*:")
RE_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")
RE_DOC_OPEN = re.compile(r'^\s*(?:[rRbBuUfF]{0,2})("""|\'\'\'|"|\')')


def _docstring_after(lines, idx):
    """Devuelve la primera frase del docstring que sigue a lines[idx] (la firma)."""
    i = idx + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return None
    line = lines[i].strip()
    if not RE_DOC_OPEN.match(line):
        return None
    # docstring de una sola linea
    m = re.match(r'^\s*(?:[rRbBuUfF]{0,2})("""|\'\'\'|"|\')(.*)$', line)
    if not m:
        return None
    quote, rest = m.group(1), m.group(2)
    if quote in ('"""', "'''"):
        body = rest
        if body.endswith(quote):
            body = body[:-3]
            return _first_sentence(body)
        # multilinea: juntar hasta cerrar
        chunk = [body]
        j = i + 1
        while j < len(lines) and quote not in lines[j]:
            chunk.append(lines[j].strip())
            j += 1
        if j < len(lines):
            chunk.append(lines[j].strip().rsplit(quote, 1)[0])
        return _first_sentence(" ".join(chunk))
    # comilla simple: puede ser multilinea
    if rest.endswith(quote):
        return _first_sentence(rest[:-1])
    chunk = [rest]
    j = i + 1
    while j < len(lines):
        chunk.append(lines[j].strip())
        if quote in lines[j]:
            break
        j += 1
    return _first_sentence(" ".join(chunk))


def _first_sentence(text):
    text = " ".join(text.split())
    if not text:
        return None
    # cortar en el primer punto seguido de espacio/fin, ignorando abreviaturas
    m = re.search(r"(?<=[a-zA-Z\)\]\}\d])\.\s", text)
    if m:
        text = text[: m.start() + 1]
    return text.strip()


def _signature(lines, idx):
    """Extrae 'nombre(params) -> retorno' de la definicion en lines[idx]."""
    buf = []
    depth = 0
    i = idx
    while i < len(lines):
        buf.append(lines[i].strip())
        depth += lines[i].count("(") - lines[i].count(")")
        if depth <= 0 and "(" in "".join(buf):
            break
        i += 1
        if i - idx > 12:
            break
    text = " ".join(buf)
    text = re.sub(r"\s+", " ", text).strip()
    # -> hasta el ':' final
    body = text.rstrip()
    if body.endswith(":"):
        body = body[:-1].rstrip()
    return body


def _decorator_kinds(lines, idx):
    """Detecta decoradores inmediatamente anteriores (p.ej. @dataclass)."""
    kinds = set()
    j = idx - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    while j >= 0 and lines[j].strip().startswith("@"):
        d = lines[j].strip()
        if "dataclass" in d:
            kinds.add("dataclass")
        j -= 1
        while j >= 0 and not lines[j].strip():
            j -= 1
    return kinds


def extract(path: Path):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    classes = []   # (name, bases, doc, indent, methods[(name, doc, is_static)])
    funcs = []    # (name, doc)
    stack = []    # (indent, class_index)
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        mc = RE_CLASS.match(raw)
        md = RE_DEF.match(raw)
        if mc:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            doc = _docstring_after(lines, i)
            bases = mc.group(4)
            classes.append({"name": mc.group(2), "bases": bases, "doc": doc,
                            "indent": indent, "methods": [],
                            "decorators": _decorator_kinds(lines, i)})
            stack.append((indent, len(classes) - 1))
            i += 1
            continue
        if md:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            doc = _docstring_after(lines, i)
            sig = _signature(lines, i)
            if stack:
                classes[stack[-1][1]]["methods"].append(
                    {"name": md.group(2), "doc": doc, "indent": indent, "sig": sig})
            else:
                funcs.append({"name": md.group(2), "doc": doc, "sig": sig})
            i += 1
            continue
        i += 1
    return classes, funcs


if __name__ == "__main__":
    import sys
    tot_c = tot_m = tot_f = 0
    for p in sorted((ROOT / "src").rglob("*.py")):
        c, f = extract(p)
        pub_m = sum(1 for cl in c for m in cl["methods"] if not m["name"].startswith("_"))
        tot_c += len(c)
        tot_m += pub_m
        tot_f += len([x for x in f if not x["name"].startswith("_")])
    print(f"clases={tot_c} metodos_publicos={tot_m} funciones_publicas={tot_f}")
    print("estimacion de lineas README:", tot_c + tot_m + tot_f)
