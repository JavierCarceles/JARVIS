#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproduce UNA mutacion y mostrar la salida CRUDA de la sonda.

Sirve para distinguir "la sonda no discrimina" de "la sonda CRASHEO con la
mutacion": en el segundo caso el parser de fallos la daria por insensible.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINE = os.path.join(ROOT, "src", "utils", "contextual_adaptation_engine.py")
PROBE = os.path.join(ROOT, "tests", "utils", "contextual_adaptation_engine",
                     "corruption_criteria_real.py")

ANTES = """        if not isinstance(fila, dict): return False
        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {}).get("real_format", {}) or {}"""
DESPUES = """        if not isinstance(fila, dict): return False
        if True: return True
        formato = (self._CORRUPTION_CRITERIA.get("files", {}).get(clave, {}) or {}).get("real_format", {}) or {}"""

with open(ENGINE, "r", encoding="utf-8") as handle:
    original = handle.read()

assert ANTES in original, "el texto a mutar no aparece"
copia = os.path.join(tempfile.gettempdir(), "engine_mutation_fila.py")
with open(copia, "w", encoding="utf-8") as handle:
    handle.write(original)

try:
    with open(ENGINE, "w", encoding="utf-8") as handle:
        handle.write(original.replace(ANTES, DESPUES, 1))
    proc = subprocess.run([sys.executable, PROBE], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=900)
finally:
    with open(ENGINE, "w", encoding="utf-8") as handle:
        handle.write(original)

print(f"returncode={proc.returncode}")
print("---- STDOUT (ultimas 40 lineas) ----")
lineas = [l for l in (proc.stdout or "").splitlines() if '"timestamp"' not in l]
print("\n".join(lineas[-40:]))
print("---- STDERR (ultimas 40 lineas) ----")
err = [l for l in (proc.stderr or "").splitlines() if '"timestamp"' not in l]
print("\n".join(err[-40:]))
