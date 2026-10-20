# -*- coding: utf-8 -*-
"""
Revierte los renombrados previos y aplica la solucion definitiva para los
5 errores de coleccion 'import file mismatch'.

DIAGNOSTICO:
  - tests/{brain,ear,eyes,hands}/test__init__.py -> 4 ficheros VACIOS con el
    MISMO basename: colisionan entre si (4-way collision).
  - tests/utils/test_cross_context_knowledge_transfer.py y
    tests/utils/test_evolutionary_strategy_optimizer.py -> VACIOS, colisionan
    con los tests REALES de tests/ (nivel raiz).
  - Todos los ficheros de tests/{brain,ear,eyes,hands,utils} estan VACIOS
    (0 bytes) tanto en HEAD como en el working tree: no aportan ni un test.

POR QUE NO "renombrar a __init__.py":
  Convertir esos directorios en paquetes crea nombres top-level (`utils`,
  `hands`, `eyes`, `ear`, `brain`) que colisionan con los paquetes reales de
  src/. Varios tests hacen sys.path.insert(0, .../src), de modo que `import
  utils` acaba resolviendo a src/utils y pytest falla con
  "No module named 'utils.test_...'". Es una bomba de relojería.

SOLUCION:
  Un unico tests/conftest.py con collect_ignore que excluye de la recoleccion
  los 5 directorios 100% vacios. No se renombra ni se borra nada de HEAD, no
  hay colision de basenames, no hay shadowing de paquetes y no se pierde
  ninguna prueba (esos ficheros no contienen ni una).
"""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

log = []

# --- 1. Revertir renombrados (test__init__.py -> __init__.py) ---------------
for d in ("brain", "ear", "eyes", "hands"):
    created = os.path.join("tests", d, "__init__.py")
    original = os.path.join("tests", d, "test__init__.py")
    if os.path.exists(created):
        if os.path.exists(original):
            os.remove(created)
            log.append("REVERTIDO: %s ya existia test__init__.py -> borrado el __init__.py" % created)
        else:
            os.rename(created, original)
            log.append("REVERTIDO: %s -> %s" % (created, original))

# --- 2. Revertir utils/__init__.py y restaurar los 2 duplicados vacios -----
if os.path.exists("tests/utils/__init__.py"):
    os.remove("tests/utils/__init__.py")
    log.append("REVERTIDO: borrado tests/utils/__init__.py")

for name in ("test_cross_context_knowledge_transfer.py",
             "test_evolutionary_strategy_optimizer.py"):
    path = os.path.join("tests", "utils", name)
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8", newline="").close()
        log.append("RESTAURADO (vacio): %s" % path)

# --- 3. Crear tests/conftest.py con collect_ignore ------------------------
CONFTEST = """# -*- coding: utf-8 -*-
\"\"\"
Configuracion de recoleccion de la suite de tests de JARVIS.

Los subdirectorios brain/, ear/, eyes/, hands/ y utils/ de tests/ contienen
unicamente ficheros VACIOS (0 bytes) comiteados en HEAD: no aportan ni una
sola prueba. Ademas:

  1. tests/{brain,ear,eyes,hands}/test__init__.py comparten basename -> los
     4 colisionan entre si ("import file mismatch").
  2. tests/utils/test_cross_context_knowledge_transfer.py y
     tests/utils/test_evolutionary_strategy_optimizer.py colisionan con los
     tests REALES que viven en tests/ (nivel raiz).

Convertirlos en paquetes (renombrarlos a __init__.py) no es una solucion
valida: crearia paquetes top-level (utils, hands, eyes, ear, brain) que
colisionan con los paquetes reales de src/, ya que varios tests insertan
'src' en sys.path.

Excluirlos de la recoleccion resuelve las colisiones sin renombrar ni borrar
ficheros de HEAD y sin perder ninguna prueba.
\"\"\"
collect_ignore = [
    "brain",
    "ear",
    "eyes",
    "hands",
    "utils",
]
"""

if not os.path.exists("tests/conftest.py"):
    with open("tests/conftest.py", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(CONFTEST)
    log.append("CREADO: tests/conftest.py (collect_ignore de los 5 dirs vacios)")
else:
    log.append("YA EXISTE: tests/conftest.py")

print("\n".join(log))
