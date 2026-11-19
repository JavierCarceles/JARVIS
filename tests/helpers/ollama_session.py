# -*- coding: ascii -*-
"""
Servidor Ollama compartido por una sesion de pytest.

El primer test que necesita Ollama llama a ``servidor_ollama_de_sesion()``
(directamente o a traves de la fixture ``ollama_server`` de
``tests/conftest.py``). Si ya hay un servidor que responde (por ejemplo, el
del usuario) se reutiliza y no se cierra nunca; si no, se arranca
``ollama serve`` una sola vez y el resto de tests de la sesion usan ese mismo
servidor, con el modelo ya cargado.

El servidor arrancado aqui se cierra al terminar la sesion
(``pytest_sessionfinish`` llama a ``cerrar_servidor_ollama_de_sesion``), al
salir del proceso (``atexit``) y, si pytest muere de golpe, lo cierra el
vigilante de ``src/core/ollama_server.py``.

Si Ollama no esta instalado o no llega a responder, la llamada lanza
``OllamaServerError`` y el test falla con ese motivo (no se salta).
"""

from __future__ import annotations

import threading
from typing import Optional

from src.core.ollama_server import OllamaServer, ensure_ollama_server

# Primer arranque: incluye iniciar el servidor (cargar un modelo es aparte).
TIEMPO_ARRANQUE_S = 60.0

_CERROJO = threading.Lock()
_SERVIDOR: Optional[OllamaServer] = None


def servidor_ollama_de_sesion() -> OllamaServer:
    """Servidor Ollama de la sesion: lo arranca la primera vez y despues lo reutiliza."""
    global _SERVIDOR
    with _CERROJO:
        if _SERVIDOR is not None and not _SERVIDOR.is_running():
            # Se cayo durante la sesion: se limpia lo que quede y se vuelve a arrancar.
            _SERVIDOR.stop()
            _SERVIDOR = None
        if _SERVIDOR is None:
            _SERVIDOR = ensure_ollama_server(timeout=TIEMPO_ARRANQUE_S)
        return _SERVIDOR


def cerrar_servidor_ollama_de_sesion() -> bool:
    """Cierra el servidor de la sesion si lo arranco ella. True si cerro uno."""
    global _SERVIDOR
    with _CERROJO:
        servidor, _SERVIDOR = _SERVIDOR, None
    return servidor.stop() if servidor is not None else False
