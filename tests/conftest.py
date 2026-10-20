# -*- coding: utf-8 -*-
"""
Configuracion de recoleccion de la suite de tests de JARVIS.

tests/ es un espejo de src/:

    src/<paquete>/<modulo>.py   ->  tests/<paquete>/test_<modulo>.py
                                    (un unico test para ese modulo)

    src/<paquete>/<modulo>.py   ->  tests/<paquete>/<modulo>/test_*.py
                                    (varios tests para ese modulo)

Añadir el path de src/ y de la raiz del proyecto aqui permite que los tests
funcionen desde cualquier profundidad de carpeta (los ficheros de test usan
rutas relativas al propio __file__ para calcular el path de src/).
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_TESTS_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")

# 'src' en el path -> "from utils.x import Y" y "from src.utils.x import Y"
for _path in (_SRC_DIR, _ROOT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)


# Los 4 ficheros test__init__.py (brain/, ear/, eyes/, hands/) estan VACIOS y
# comparten basename -> pytest falla con "import file mismatch" si se recolectan.
# Se ignoran de forma explicita (no se borra ningun fichero).
collect_ignore = [
    "brain/test__init__.py",
    "ear/test__init__.py",
    "eyes/test__init__.py",
    "hands/test__init__.py",
]
