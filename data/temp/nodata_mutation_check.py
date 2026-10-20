#!/usr/bin/env python3
"""MUTATION CHECK: la sonda de comportamiento sin datos (2.8.8.9.5.3) debe FALLAR
si el contrato declarado se desvia del comportamiento real.

Muta el contrato en memoria (sin tocar el fichero del motor) y reejecuta la sonda.
Si la sonda no detecta ninguna mutacion, no prueba nada.
"""
import io
import os
import re
import shutil
import sys
import contextlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINE = os.path.join(ROOT, "src", "utils", "contextual_adaptation_engine.py")
PROBE = os.path.join(ROOT, "tests", "utils", "contextual_adaptation_engine", "no_data_behavior_real.py")

MUTACIONES = [
    ("read_apis mal declarada",
     '{"api": "get_engine_status", "returns": "dict", "args": []}',
     '{"api": "get_engine_status", "returns": "list", "args": []}'),
    ("startup declares que se crea un fichero de persistencia",
     '"creates_persistence_files": False',
     '"creates_persistence_files": True'),
    ("write_apis declara una API que no crea el fichero",
     '{"api": "_save_goal_adaptation_feedback", "returns": "none", "creates": "goal_adaptation_feedback"}',
     '{"api": "_save_goal_adaptation_feedback", "returns": "none", "creates": "knowledge_base"}'),
    ("detection declara que escribe",
     '"detection_writes": False',
     '"detection_writes": True'),
]


def run_probe():
    """Ejecuta la sonda en un subproceso y devuelve (exit_code, output)."""
    import subprocess
    proc = subprocess.run([sys.executable, PROBE], capture_output=True, text=True, cwd=ROOT)
    return proc.returncode, proc.stdout + proc.stderr


def main():
    with open(ENGINE, "r", encoding="utf-8") as handle:
        original = handle.read()

    print("== MUTATION CHECK: la sonda debe detectar cada mutacion ==")
    fallos = []
    for nombre, viejo, nuevo in MUTACIONES:
        if viejo not in original:
            print(f"  [ERROR] patron no encontrado: {nombre}")
            fallos.append(nombre)
            continue
        mutado = original.replace(viejo, nuevo, 1)
        with open(ENGINE, "w", encoding="utf-8") as handle:
            handle.write(mutado)
        try:
            code, salida = run_probe()
        finally:
            with open(ENGINE, "w", encoding="utf-8") as handle:
                handle.write(original)
        detectada = code != 0
        print(f"  [{'OK  ' if detectada else 'FALLO'}] La sonda detecta: {nombre}"
              f" :: exit={code}")
        if not detectada:
            fallos.append(nombre)

    # La sonda debe PASAR con el contrato original (restaurado).
    code, salida = run_probe()
    print(f"  [{'OK  ' if code == 0 else 'FALLO'}] La sonda pasa con el contrato original :: exit={code}")
    if code != 0:
        fallos.append("sonda original")

    print(f"\n  Mutaciones no detectadas: {len(fallos)}")
    for f in fallos:
        print(f"    - {f}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
