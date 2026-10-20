# -*- coding: utf-8 -*-
"""
Corrige los 5 errores de coleccion 'import file mismatch'.

Causa raiz: todos los ficheros de tests/{ear,eyes,hands,brain,utils} estan
VACIOS (0 bytes). Los 4 'test__init__.py' colisionan entre si (mismo basename
en 4 directorios) y los 2 de tests/utils/ colisionan con los tests REALES
que viven en tests/ (nivel raiz).

Solucion:
  1. Renombrar test__init__.py -> __init__.py (marcador de paquete real,
     que es lo que el autor pretendia; vacios, luego no se pierde nada).
  2. Crear tests/utils/__init__.py (consistencia con el resto de subdirs).
  3. Eliminar los 2 duplicados vacios de tests/utils/ (su contenido real
     ya esta en tests/ nivel raiz: 27094 B y 47358 B).
"""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

RENAMES = [
    ("tests/brain/test__init__.py", "tests/brain/__init__.py"),
    ("tests/ear/test__init__.py", "tests/ear/__init__.py"),
    ("tests/eyes/test__init__.py", "tests/eyes/__init__.py"),
    ("tests/hands/test__init__.py", "tests/hands/__init__.py"),
]

CREATE = [("tests/utils/__init__.py", "")]

# Duplicados vacios: se eliminan solo si siguen vacios (0 bytes) y si el
# original de verdad existe con contenido.
DELETE = [
    ("tests/utils/test_cross_context_knowledge_transfer.py",
     "tests/test_cross_context_knowledge_transfer.py"),
    ("tests/utils/test_evolutionary_strategy_optimizer.py",
     "tests/test_evolutionary_strategy_optimizer.py"),
]

log = []
for src, dst in RENAMES:
    if os.path.exists(src) and os.path.getsize(src) == 0:
        if os.path.exists(dst):
            os.remove(src)
            log.append("BORRADO(sustituido por %s): %s" % (dst, src))
        else:
            os.rename(src, dst)
            log.append("RENOMBRADO: %s -> %s" % (src, dst))
    else:
        log.append("OMITIDO (no existe o no vacio): %s" % src)

for path, content in CREATE:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        log.append("CREADO: %s" % path)
    else:
        log.append("YA EXISTE: %s" % path)

for dup, original in DELETE:
    if os.path.exists(dup) and os.path.getsize(dup) == 0 and os.path.exists(original) and os.path.getsize(original) > 0:
        os.remove(dup)
        log.append("BORRADO (duplicado vacio de %s): %s" % (original, dup))
    elif not os.path.exists(dup):
        log.append("YA NO EXISTE: %s" % dup)
    else:
        log.append("OMITIDO (no vacio o falta original): %s" % dup)

print("\n".join(log))
