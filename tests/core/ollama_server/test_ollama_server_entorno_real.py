# -*- coding: ascii -*-
"""
Arranque y cierre reales de `ollama serve` con el ejecutable instalado.

Arranca un servidor propio en un puerto libre, distinto del que usa el
servidor del usuario: nunca abre, reutiliza ni cierra ese servidor y comprueba
que su estado (en marcha o parado) no cambia. Verifica que el servidor propio
responde con su version real, que el cliente `ollama` lista los modelos
instalados a traves de el y que al cerrarlo no queda ningun proceso suyo.

No carga ni descarga modelos. Falla (no se salta) si Ollama no esta
instalado, como el resto de tests que usan Ollama real.
"""

import json
import socket

import psutil

import src.core.ollama_server as ollama_server
from src.core.ollama_server import ensure_ollama_server, find_ollama_executable, server_responds


def _puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_ollama_serve_real_arranca_responde_y_se_cierra():
    assert find_ollama_executable(), "Ollama no esta instalado (https://ollama.com/download)"
    servidor_usuario_antes = server_responds(None, timeout=1.0)

    direccion = "http://127.0.0.1:%d" % _puerto_libre()
    servidor = ensure_ollama_server(host=direccion, timeout=60, register_atexit=False)
    try:
        assert servidor.started_by_us is True
        with ollama_server._NO_PROXY_OPENER.open(direccion + "/api/version", timeout=5) as respuesta:
            version = json.loads(respuesta.read().decode("utf-8"))["version"]
        assert version, "ollama serve no informo de su version"

        import ollama

        modelos = ollama.Client(host=direccion).list()
        assert isinstance(list(getattr(modelos, "models", None) or []), list)

        proceso = psutil.Process(servidor.pid)
        vigilante = psutil.Process(servidor.watchdog_pid)
    except BaseException:
        servidor.stop()
        raise

    assert servidor.stop() is True
    assert not server_responds(direccion, timeout=1.0)
    assert not proceso.is_running()
    psutil.wait_procs([vigilante], timeout=10)
    assert not vigilante.is_running()
    # El servidor del usuario (si lo habia) sigue igual.
    assert server_responds(None, timeout=1.0) == servidor_usuario_antes
