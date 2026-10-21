import pathlib
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[2]
t = (ROOT / "data/temp/README_generated.md").read_text(encoding="utf-8")
ents = re.findall(r"^#### .*?`([^`]+\.py)`", t, re.M)
src = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "src").rglob("*.py"))
print("entradas:", len(ents), "| unicas:", len(set(ents)), "| src:", len(src))
print("faltan:", [p for p in src if p not in set(ents)])
print("duplicados:", [p for p, c in Counter(ents).items() if c > 1])
print("huerfanos:", [p for p in set(ents) if p not in src])
print("--- terminologia narrativa ---")
for w in ["Estructura de", "estructura", "Estrategia", "estrategia", "Alcance",
          "Sonda", "sonda", "Contrato", "contrato", "Criterios", "Hallazgo",
          "Notas", "Verificacion", "Verificación", "seccion ausente",
          "almacenamiento ausente", "2.8.8.9"]:
    print(f"  {w}: {t.count(w)}")
print("--- tamano ---")
print("lineas:", len(t.splitlines()), "| bytes:", len(t.encode("utf-8")))
print("--- lineas de descripcion vacias ---")
print("  '- **Descripción**: -':", t.count("- **Descripción**: -"))
