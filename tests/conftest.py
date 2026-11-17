# -*- coding: utf-8 -*-
"""
Configuracion de recoleccion de la suite de tests de JARVIS.

tests/ replica la estructura de src/ (por ejemplo src/hands/apps/ ->
tests/hands/apps/). Ver docs/readme/README_TESTS.md.

Se anaden la raiz del proyecto y src/ a sys.path para que los tests funcionen
desde cualquier profundidad de carpeta. Todos los imports usan el prefijo
"src." (from src.core.config import ...).
"""

import logging
import os
import sys
import tempfile

import pytest  # noqa: E402

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_TESTS_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")

# CWD original (se captura al importar el conftest, antes de cualquier sandbox)
_CWD_ORIGINAL = os.getcwd()

# Raiz del proyecto en el path -> "from src.x import Y" y "from tests.helpers import Y"
for _path in (_SRC_DIR, _ROOT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)


# Los 4 ficheros test__init__.py (brain/, ear/, eyes/, hands/) comparten
# basename -> pytest falla con "import file mismatch" si se recolectan todos.
# Se ignoran de forma explicita. Los de brain/, ear/ y eyes/ contienen tests que
# por ello no se ejecutan (ver docs/readme/README_TESTS.md, problemas conocidos).
collect_ignore = [
    "brain/test__init__.py",
    "ear/test__init__.py",
    "eyes/test__init__.py",
    "hands/test__init__.py",
]


# ---------------------------------------------------------------------------
# AISLAMIENTO DEL CWD (sandbox global de la suite)
# ---------------------------------------------------------------------------
# Varios modulos (sobre todo los de src/experimental/) escriben con RUTAS
# RELATIVAS ('data/knowledge_graph.json', 'data/improvement_rules.json',
# 'models/...') resueltas contra el CWD. Sin un sandbox, la suite modificaria el
# `data/` de PRODUCCION del repo.
#
# Se ejecuta toda la sesion dentro de un temporal, de modo que ninguna ruta
# relativa al CWD pueda tocar el repo. Las rutas ABSOLUTAS (calculadas con
# __file__) siguen apuntando a produccion, que es lo que los tests deben leer.
_SANDBOX_DIR = tempfile.mkdtemp(prefix="jarvis_pytest_sandbox_")
for _sub in ("data", "models", "logs", "config"):
    os.makedirs(os.path.join(_SANDBOX_DIR, _sub), exist_ok=True)

_SANDBOX_ACTIVO = False


def pytest_configure(config):
    """Absolutiza los argumentos de coleccion y activa el sandbox.

    pytest resuelve los argumentos de coleccion de forma RELATIVA al CWD
    durante la recoleccion, que ocurre DESPUES de este hook. Por eso las
    rutas se absolutizan ANTES de cambiar el CWD (y siempre contra el CWD
    original, no contra el sandbox).
    """
    global _SANDBOX_ACTIVO
    if not _SANDBOX_ACTIVO:
        for _i, _arg in enumerate(config.args):
            if not isinstance(_arg, str) or _arg.startswith("-"):
                continue
            _head, _sep, _tail = _arg.partition("::")
            _cand = os.path.join(_CWD_ORIGINAL, _head)
            if os.path.exists(_cand):
                config.args[_i] = _cand + _sep + _tail
        _SANDBOX_ACTIVO = True
    os.chdir(_SANDBOX_DIR)


def pytest_sessionfinish(session, exitstatus):
    """Vuelve al sandbox: pytest restaura el CWD original en su `finally`.

    `pytest.main.wrap_session` hace `os.chdir(session.startpath)` ANTES de
    llamar a este hook. Los hilos de los loggers siguen vivos y escriben
    `logs/jarvis_logs.db` con ruta RELATIVA, de modo que al restaurarse el
    CWD del repo terminarian escribiendo en `logs/` de PRODUCCION.
    """
    os.chdir(_SANDBOX_DIR)
    # Al cerrar la sesion, pytest ya ha cerrado el stream de captura: los
    # `__del__` de los singletons de `utils` loguean a un fichero cerrado y
    # Python imprime "--- Logging error ---" (ruido de apagado, no un fallo).
    logging.raiseExceptions = False


# ---------------------------------------------------------------------------
# AISLAMIENTO DE SINGLETONS GLOBALES ENTRE PRUEBAS (unidad 3.8.4.7.3)
# ---------------------------------------------------------------------------
# `get_application_manager()` (src/hands/apps/applications_core.py),
# `get_memory_manager()` (src/memory/storage.py) y
# `get_application_knowledge_integrator()` (src/hands/planner/application_integration.py)
# son singletons de proceso con estado mutable. El integrador guarda en
# `application_manager` una referencia al `ApplicationManager` en su `__init__`
# (linea 47), por lo que reiniciar solo `_app_manager` no basta: `Brain` y el
# `Planner` leen el catalogo a traves del integrador y seguirian viendo el
# manager previo. Una prueba que muta el catalogo -p. ej.
# `test_brain_consumer_with_minimal_app_in_catalog`, que agrega "testminapp"
# al catalogo del singleton y solo lo restaura en su `finally`- deja residuos
# que afectan a pruebas posteriores segun el orden de ejecucion.
#
# Este fixture `autouse` de ambito de funcion reinicia los tres singletons
# antes de CADA prueba y al finalizarla, de modo que:
#   * Cada prueba parte de un `ApplicationManager` fresco (catalogo limpio:
#     chrome/spotify + entidades reconstruidas de `data/memory/entities.json`,
#     leidas solo-lectura), sin residuos de pruebas previas.
#   * Ninguna prueba debilita sus aserciones: el `MemoryManager` fresco lee
#     `data/memory/` de forma solo-lectura para `_load_custom_applications`;
#     las pruebas que escriben usan stubs propios o `MemoryManager(tmp_path)`.
#   * El estado global compartido queda aislado, eliminando la falla por orden
#     de ejecucion y haciendo el resultado independiente del orden de pruebas.
#
# Nota: el `MemoryManager` del singleton se deja en None para que se recree
# con su ruta por defecto (`data/memory/`), porque
# `_initialize_applications() -> _load_custom_applications()` necesita leer
# `entities.json` (YouTube, GitHub, Twitch...) y pruebas como
# `test_application_consumers_real_model.py` dependen de ese catalogo real.
@pytest.fixture(autouse=True)
def _reset_global_singletons_between_tests():
    import src.hands.apps.applications_core as _applications_core_mod  # noqa: E402
    import src.memory.storage as _storage_mod  # noqa: E402
    import src.hands.planner.application_integration as _app_integration_mod  # noqa: E402

    _applications_core_mod._app_manager = None
    _storage_mod._memory_manager = None
    _app_integration_mod._app_integrator = None

    yield

    # Teardown defensivo: si la prueba termina con error antes de restaurar el
    # estado ella misma, la siguiente prueba parte de singletons limpios.
    _applications_core_mod._app_manager = None
    _storage_mod._memory_manager = None
    _app_integration_mod._app_integrator = None
