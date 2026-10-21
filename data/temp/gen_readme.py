"""
Genera el README de JARVIS a partir del codigo real de src/.

Regla de contenido: solo informacion de los ficheros de src/
  - descripcion de funcionalidad de cada fichero
  - definicion de sus clases (nombre, tipo, proposito)
  - definicion de sus metodos y funciones (firma + proposito)
No se incluyen explicaciones de estructuras, estrategias, alcances ni trazas
de verificacion: eso no es informacion del fichero.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_code import extract, ROOT  # noqa: E402

README = ROOT / "README.md"
SRC = ROOT / "src"

RE_ENTRY = re.compile(
    r"^####\s+.*?`([^`]+\.py)`\s*(?:\[[^\]]*\])?\s*(?:-\s*(.*))?$"
)
RE_ITEM = re.compile(r"^\s*-\s+`([^`]+)`\s*(?:\(([^)]*)\))?\s*:\s*(.*)$")
RE_BULLET = re.compile(r"^\s*-\s+\*\*(.+?)\*\*\s*:?\s*(.*)$")

KIND_WORDS = {"Enum", "dataclass", "BaseModel", "class", "NamedTuple", "TypedDict"}


# --------------------------------------------------------------------------
# 1. Lectura del README actual (fuente de titulos y descripciones)
# --------------------------------------------------------------------------
def _keep_longer(old, new):
    return new if len(new) > len(old) else old


def parse_readme():
    lines = README.read_text(encoding="utf-8").splitlines()
    entries, order, module_titles = {}, [], {}
    cur, section = None, None
    mod = None
    for l in lines:
        if l.startswith("### "):
            mod = l
            module_titles.setdefault(mod, None)
            continue
        m = RE_ENTRY.match(l)
        if m:
            path, title = m.group(1), (m.group(2) or "").strip()
            if path not in entries:
                entries[path] = {
                    "path": path, "title": title, "desc": "", "module": mod,
                    "classes": {}, "methods": {}, "funcs": {},
                }
                order.append(path)
            cur = entries[path]
            if title and len(title) > len(cur["title"]):
                cur["title"] = title
            section = None
            continue
        if cur is None:
            continue
        b = RE_BULLET.match(l)
        if b:
            label, rest = b.group(1).strip().lower(), b.group(2).strip()
            if label.startswith("descripci"):
                if rest:
                    cur["desc"] = _keep_longer(cur["desc"], rest)
                section = "desc"
            elif "clase" in label:
                section = "classes"
            elif "todo" in label and "metod" in label:
                section = "methods"
            elif "funci" in label:
                section = "funcs"
            else:
                section = None
            continue
        it = RE_ITEM.match(l)
        if it and section in ("classes", "methods", "funcs"):
            name = it.group(1)
            kind = (it.group(2) or "").strip()
            text = it.group(3).strip()
            if kind and kind not in KIND_WORDS:
                kind = ""
            bucket = cur[section]
            prev = bucket.get(name)
            if prev is None:
                bucket[name] = {"kind": kind, "text": text}
            else:
                if kind and not prev["kind"]:
                    prev["kind"] = kind
                prev["text"] = _keep_longer(prev["text"], text)
    return entries, order, module_titles


# --------------------------------------------------------------------------
# 2. Datos del codigo
# --------------------------------------------------------------------------
def code_facts(path):
    return extract(ROOT / path)


def class_kind(c):
    bases = c.get("bases") or ""
    decs = c.get("decorators") or set()
    if "dataclass" in decs:
        return "dataclass"
    base_names = [b.strip().split("(")[0].strip() for b in bases.split(",")]
    joined = " ".join(base_names)
    if "Enum" in joined or "IntEnum" in joined or "StrEnum" in joined:
        return "Enum"
    if "BaseModel" in joined:
        return "BaseModel"
    if "dataclass" in bases:
        return "dataclass"
    if "NamedTuple" in joined:
        return "NamedTuple"
    if "TypedDict" in joined:
        return "TypedDict"
    return "class"


def clean(text):
    if not text:
        return ""
    return " ".join(text.split()).strip()


def sig_label(sig, qualified, plain):
    """'def m(params) -> ret' -> 'Clase.m(params) -> ret' como etiqueta markdown."""
    if not sig:
        return f"`{qualified}`"
    sig = sig.strip()
    if sig.startswith("def "):
        sig = sig[4:].strip()
    if sig.startswith("async "):
        sig = sig[6:].strip()
    if sig.startswith(plain):
        tail = sig[len(plain):]
    else:
        tail = ""
    if tail and not tail.startswith("("):
        tail = f"({tail})"
    return f"`{qualified}{tail}`"


# --------------------------------------------------------------------------
# 3. Generacion
# --------------------------------------------------------------------------
MODULE_ORDER = [
    "src/", "src/brain/", "src/ear/", "src/eyes/", "src/hands/",
    "src/hands/chrome/", "src/hands/edge/", "src/hands/firefox/",
    "src/hands/planner/", "src/hands/windows/", "src/memory/", "src/mouth/",
    "src/tools/", "src/utils/",
]

MODULE_TITLES = {
    "src/": "### \U0001F4C1 Módulo `src/` - Directorio Principal del Sistema",
    "src/brain/": "### \U0001F9E0 Módulo `src/brain/` - Cerebro Central",
    "src/ear/": "### \U0001F442 Módulo `src/ear/` - Sistema de Escucha",
    "src/eyes/": "### \U0001F441️ Módulo `src/eyes/` - Sistema de Visión",
    "src/hands/": "### \U0001F916 Módulo `src/hands/` - Sistema de Ejecución",
    "src/hands/chrome/": "### \U0001F9E9 Módulo `src/hands/chrome/` - Acciones de Google Chrome",
    "src/hands/edge/": "### \U0001F9E9 Módulo `src/hands/edge/` - Acciones de Microsoft Edge",
    "src/hands/firefox/": "### \U0001F9E9 Módulo `src/hands/firefox/` - Acciones de Mozilla Firefox",
    "src/hands/planner/": "### \U0001F9E9 Módulo `src/hands/planner/` - Planificación Jerárquica",
    "src/hands/windows/": "### \U0001F9E9 Módulo `src/hands/windows/` - Acciones de Windows",
    "src/memory/": "### \U0001F5C3️ Módulo `src/memory/` - Sistema de Memoria y Planificación",
    "src/mouth/": "### \U0001F5E3️ Módulo `src/mouth/` - Sistema de Voz",
    "src/tools/": "### \U0001F6E0️ Módulo `src/tools/` - Sistema de Herramientas",
    "src/utils/": "### \U0001F5C2️ Módulo `src/utils/` - Utilidades del Sistema",
}


def module_docstring(path):
    lines = (ROOT / path).read_text(encoding="utf-8-sig").splitlines()
    for i, l in enumerate(lines):
        if l.strip().startswith('"""'):
            body = l.strip()[3:]
            if body.endswith('"""'):
                return clean(body[:-3])
            chunk = [body]
            j = i + 1
            while j < len(lines) and '"""' not in lines[j]:
                chunk.append(lines[j].strip())
                j += 1
            if j < len(lines):
                chunk.append(lines[j].strip().split('"""')[0])
            return clean(" ".join(chunk))
    return ""


def render_file(path, old):
    old = old or {}
    classes, funcs = code_facts(path)
    nlines = len((ROOT / path).read_text(encoding="utf-8-sig").splitlines())

    title = old.get("title") or ""
    if not title:
        title = path.rsplit("/", 1)[-1].replace(".py", "").replace("_", " ").title()

    desc = clean(old.get("desc", ""))
    if len(desc) < 25:
        mod_doc = module_docstring(path)
        if mod_doc:
            desc = mod_doc

    out = [f"#### `{path}` [{nlines} líneas] - {title}"]
    out.append(f"- **Descripción**: {desc}" if desc else "- **Descripción**: -")

    if classes:
        out.append("- **Clases principales**:")
        for c in classes:
            kind = class_kind(c)
            prev = old.get("classes", {}).get(c["name"], {})
            text = clean(prev.get("text", "")) or clean(c["doc"] or "")
            label = f"`{c['name']}` ({kind})" if kind != "class" else f"`{c['name']}`"
            out.append(f"  - {label}: {text}" if text else f"  - {label}")

    methods = []
    for c in classes:
        for m in c["methods"]:
            if m["name"].startswith("_") and m["name"] != "__init__":
                continue
            methods.append((c["name"], m))
    if methods:
        out.append("- **Métodos principales**:")
        for cname, m in methods:
            prev = old.get("methods", {}).get(f"{cname}.{m['name']}")
            if not prev:
                prev = old.get("methods", {}).get(m["name"])
            text = clean(prev.get("text", "") if prev else "") or clean(m["doc"] or "")
            label = sig_label(m.get("sig"), f"{cname}.{m['name']}", m["name"])
            out.append(f"  - {label}: {text}" if text else f"  - {label}")

    pub_funcs = [f for f in funcs if not f["name"].startswith("_")]
    if pub_funcs:
        out.append("- **Funciones globales**:")
        for f in pub_funcs:
            prev = old.get("funcs", {}).get(f["name"])
            text = clean(prev.get("text", "") if prev else "") or clean(f["doc"] or "")
            label = sig_label(f.get("sig"), f["name"], f["name"])
            out.append(f"  - {label}: {text}" if text else f"  - {label}")

    out.append("")
    return out


def build():
    entries, order, _ = parse_readme()
    out = []
    out.append("# JARVIS - Asistente de IA con Planificación Jerárquica")
    out.append("")
    out.append("## Arquitectura del Proyecto")
    out.append("")
    out.append(
        "Documentación de los ficheros de `src/`: qué hace cada fichero, "
        "qué clases define y qué métodos expone."
    )
    out.append("")

    all_src = sorted(p.relative_to(ROOT).as_posix() for p in SRC.rglob("*.py"))
    by_module = {m: [] for m in MODULE_ORDER}
    for p in all_src:
        mod = p.rsplit("/", 1)[0] + "/"
        by_module.setdefault(mod, []).append(p)

    for mod in MODULE_ORDER:
        files = by_module.get(mod) or []
        if not files:
            continue
        out.append(MODULE_TITLES.get(mod, f"### 📦 Módulo `{mod}`"))
        out.append("")
        for path in files:
            out.extend(render_file(path, entries.get(path)))
        if out and out[-1] == "":
            out.pop()
        out.append("")
    return "\n".join(out).rstrip() + "\n"


if __name__ == "__main__":
    out = build()
    out_path = Path(__file__).resolve().parent / "README_generated.md"
    out_path.write_text(out, encoding="utf-8")
    print("lineas generadas:", len(out.splitlines()))
    print("bytes:", len(out.encode("utf-8")))
    print("mojibake A-circ:", out.count("\u00c3"), "| replacement:", out.count("\ufffd"))
