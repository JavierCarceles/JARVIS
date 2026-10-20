#!/usr/bin/env python3
"""Escaneo exhaustivo de referencias a fases en README.md (sobre el fichero real en disco)."""

import hashlib
import os
import re

PATH = os.path.abspath("README.md")

with open(PATH, "rb") as handle:
    raw = handle.read()

print("RESULTADO ruta=%s" % PATH)
print("RESULTADO bytes=%d mtime=%s" % (len(raw), os.path.getmtime(PATH)))
print("RESULTADO sha256=%s" % hashlib.sha256(raw).hexdigest()[:16])
print("RESULTADO decodifica_utf8=%s" % (raw.decode("utf-8", "replace") is not None))

text = raw.decode("utf-8", "replace")
low = text.lower()

TERMS = [
    "fase", "fases", "subfase", "sub-fase", "sub fase", "phase", "etapa",
    "etapas", "stage", "stages", "hoja", "hojas", "unidad", "unidades",
    "milestone", "hito", "sprint", "epic", "epica", "iteracion", "iteración",
    "mejora incremental", "supercomplete", "roadmap", "backlog",
    "siguiente unidad", "hoja actual", "fase actual", "estado de la mejora",
    "trabajo pendiente", "ciclo de mejora", "automejora incremental",
    "2.8.", "1.1.", "v2.8", "item 5", "item 1",
]
for term in TERMS:
    count = low.count(term.lower())
    if count:
        print("RESULTADO HIT %-26s = %d" % (term, count))

print("RESULTADO --- detalle de coincidencias ---")
lines = text.replace("\r\n", "\n").split("\n")
found = 0
for index, line in enumerate(lines):
    for term in ("fase", "phase", "etapa", "hoja", "roadmap", "supercomplete"):
        if term in line.lower():
            found += 1
            print("RESULTADO L%-5d [%s] %s" % (
                index + 1, term,
                line.strip()[:160].encode("ascii", "replace").decode()))
            break
print("RESULTADO lineas_con_match=%d" % found)

# UTF-16 / variantes de codificacion
for enc in ("utf-16", "utf-16-le", "utf-16-be"):
    try:
        alt = raw.decode(enc, "ignore").lower()
        n = alt.count("fase")
        if n:
            print("RESULTADO ENCODING %s -> fase=%d" % (enc, n))
    except Exception:
        pass
