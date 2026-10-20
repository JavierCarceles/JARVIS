#!/usr/bin/env python3
"""Verifica que la sonda 2.8.8.9.5.3 NO modifica el `data/` de produccion.

Compara el sha256 de los ficheros de persistencia y de `data/knowledge_graph.json`
antes y después de ejecutar la sonda.
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROBE = os.path.join(ROOT, "tests", "utils", "contextual_adaptation_engine", "no_data_behavior_real.py")

FICHEROS = [
    "data/contextual_adaptation_rules.json",
    "data/contextual_knowledge_base.json",
    "data/goal_adaptation_feedback.json",
    "data/goal_adaptation_learning_results.json",
    "data/knowledge_graph.json",
]


def sha(ruta):
    if not os.path.isfile(ruta):
        return "AUSENTE"
    h = hashlib.sha256()
    with open(ruta, "rb") as handle:
        for bloque in iter(lambda: handle.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def main():
    antes = {f: sha(os.path.join(ROOT, f)) for f in FICHEROS}
    proc = subprocess.run([sys.executable, PROBE], capture_output=True, text=True, cwd=ROOT)
    despues = {f: sha(os.path.join(ROOT, f)) for f in FICHEROS}

    print(f"  sonda exit={proc.returncode}")
    iguales = True
    for f in FICHEROS:
        ok = antes[f] == despues[f]
        iguales = iguales and ok
        print(f"  [{'OK  ' if ok else 'FALLO'}] {f} :: {antes[f][:16]} -> {despues[f][:16]}")
    print(f"\n  data/ de produccion intacto: {iguales}")
    return 0 if (iguales and proc.returncode == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
