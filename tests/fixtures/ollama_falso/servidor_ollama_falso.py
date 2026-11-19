# -*- coding: ascii -*-
"""
Servidor Ollama falso para probar src/core/ollama_server.py con procesos reales.

Uso (como lo lanza ensure_ollama_server con command=[python, este_fichero]):

    python servidor_ollama_falso.py serve

Escucha en la direccion de OLLAMA_HOST (host:puerto), responde GET
/api/version y /api/tags como Ollama y lanza un proceso hijo que imita a un
runner de modelos, para comprobar que el cierre alcanza a todo el arbol de
procesos. No carga modelos ni toca el servidor Ollama real del equipo.

OLLAMA_FALSO_MODO cambia el comportamiento:
    fallo -> escribe un error de puerto ocupado y termina con codigo 1
    mudo  -> arranca el runner pero nunca abre el puerto
"""

import http.server
import json
import os
import subprocess
import sys
import time

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_VIDA_RUNNER_S = 600


class _Manejador(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (API de http.server)
        if self.path == "/api/version":
            cuerpo = {"version": "0.0.0-falso"}
        elif self.path == "/api/tags":
            cuerpo = {"models": []}
        else:
            self.send_error(404)
            return
        datos = json.dumps(cuerpo).encode("ascii")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *args):
        pass


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "serve":
        print("uso: servidor_ollama_falso.py serve", file=sys.stderr)
        return 2
    modo = os.environ.get("OLLAMA_FALSO_MODO", "")
    if modo == "fallo":
        print("Error: listen tcp: bind: address already in use (servidor falso)", file=sys.stderr, flush=True)
        return 1

    runner = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(%d)" % _VIDA_RUNNER_S],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_SIN_VENTANA,
    )
    print("runner %d" % runner.pid, flush=True)
    if modo == "mudo":
        while True:
            time.sleep(1)

    host, _, puerto = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").rpartition(":")
    servidor = http.server.ThreadingHTTPServer((host.strip("[]") or "127.0.0.1", int(puerto)), _Manejador)
    print("escuchando %s:%s" % (host, puerto), flush=True)
    servidor.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
