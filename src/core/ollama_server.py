# src/core/ollama_server.py
"""
Arranque y cierre del servidor local de Ollama (``ollama serve``).

``ensure_ollama_server()`` comprueba si responde el servidor configurado
(``OLLAMA_HOST``, por defecto ``http://127.0.0.1:11434``, con la misma regla
que el cliente ``ollama``):

* Si responde, lo reutiliza y NUNCA lo cierra: puede ser el del usuario o el
  de otro proceso. Devuelve un ``OllamaServer`` con ``started_by_us=False``.
* Si no responde y la direccion es local, ejecuta ``ollama serve`` como
  proceso propio (argumentos estructurados, sin shell y sin ventana de
  consola en Windows), espera a que conteste y devuelve un ``OllamaServer``
  con ``started_by_us=True``.
* Si la direccion no es local, o no se encuentra el ejecutable, o el
  servidor no llega a responder, lanza ``OllamaServerError`` con el motivo.

Un servidor arrancado aqui se cierra, junto con sus procesos hijos (los
runners que cargan los modelos):

1. al llamar a ``OllamaServer.stop()`` (idempotente);
2. al salir del interprete (``atexit``), si no se habia cerrado antes;
3. si el proceso que lo arranco muere sin poder limpiar (cierre forzado), lo
   cierra un vigilante: un proceso Python aparte
   (``python -m src.core.ollama_server --watch ...``) que comprueba cada
   segundo que su creador sigue vivo.

Antes de terminar un proceso se comprueba su identidad (PID y hora de
creacion), de modo que nunca se cierra un proceso ajeno que haya reutilizado
el PID. Nunca descarga modelos.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence

import psutil

from src.core.log import get_logger

logger = get_logger(__name__)

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_PORT = 11434

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}
# Sin ventana de consola para los procesos hijos en Windows (0 en el resto).
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CREATE_TIME_TOLERANCE_S = 0.01
_LOG_TAIL_CHARS = 2000
_WATCH_INTERVAL_S = 1.0

# Las comprobaciones de salud nunca pasan por un proxy del sistema.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaServerError(RuntimeError):
    """No se pudo disponer de un servidor Ollama que responda."""


# ============================================================================
# DIRECCION DEL SERVIDOR
# ============================================================================


def resolve_host(host: Optional[str] = None) -> str:
    """URL base del servidor (``host`` o ``OLLAMA_HOST``) con la regla del cliente ``ollama``."""
    value = host if host is not None else os.environ.get("OLLAMA_HOST")
    try:
        from ollama._client import _parse_host  # misma interpretacion que ollama.chat()

        return _parse_host(value)
    except Exception as exc:
        logger.debug("[OLLAMA] Interpretacion propia de la direccion %r: %s", value, exc)
        return _fallback_parse_host(value)


def _fallback_parse_host(value: Optional[str]) -> str:
    text = (value or "").strip()
    if not text:
        return DEFAULT_HOST
    if "://" not in text:
        text = "http://" + text
    parts = urllib.parse.urlsplit(text)
    hostname = parts.hostname or "127.0.0.1"
    if ":" in hostname:
        hostname = "[%s]" % hostname
    return "%s://%s:%s%s" % (parts.scheme or "http", hostname, parts.port or DEFAULT_PORT, parts.path.rstrip("/"))


def _split_url(url: str) -> urllib.parse.SplitResult:
    return urllib.parse.urlsplit(url if "://" in url else "http://" + url)


def is_local_host(url: str) -> bool:
    """True si la direccion apunta a este equipo (solo entonces se arranca un servidor)."""
    hostname = (_split_url(url).hostname or "127.0.0.1").lower()
    return hostname in _LOCAL_HOSTNAMES or hostname.startswith("127.")


def _bind_address(url: str) -> str:
    """``host:puerto`` para la variable ``OLLAMA_HOST`` de ``ollama serve``."""
    parts = _split_url(url)
    hostname = parts.hostname or "127.0.0.1"
    if ":" in hostname:
        hostname = "[%s]" % hostname
    return "%s:%s" % (hostname, parts.port or DEFAULT_PORT)


def _probe_base(url: str) -> str:
    """URL para conectarse: una direccion de escucha comodin se sondea en el bucle local."""
    parts = _split_url(url)
    hostname = parts.hostname or "127.0.0.1"
    if hostname == "0.0.0.0":
        hostname = "127.0.0.1"
    elif hostname == "::":
        hostname = "::1"
    if ":" in hostname:
        hostname = "[%s]" % hostname
    return "%s://%s:%s%s" % (parts.scheme or "http", hostname, parts.port or DEFAULT_PORT, parts.path.rstrip("/"))


def server_responds(host: Optional[str] = None, timeout: float = 2.0) -> bool:
    """True si ``GET /api/version`` del servidor contesta con un JSON que incluye ``version``."""
    url = _probe_base(resolve_host(host))
    try:
        with _NO_PROXY_OPENER.open(url + "/api/version", timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return False
            data = json.loads(response.read().decode("utf-8", "replace") or "{}")
        return isinstance(data, dict) and "version" in data
    except Exception as exc:
        logger.debug("[OLLAMA] %s no responde: %s", url, exc)
        return False


# ============================================================================
# EJECUTABLE Y PROCESOS
# ============================================================================


def find_ollama_executable() -> Optional[str]:
    """Ruta del ejecutable ``ollama``: el del PATH o, si no esta, la instalacion por usuario.

    La instalacion oficial por usuario de Windows deja el programa en
    ``%LOCALAPPDATA%/Programs/Ollama`` y lo anade al PATH, pero una consola
    abierta antes de instalar no ve ese PATH.
    """
    found = shutil.which("ollama")
    if found:
        return found
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidate = Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _same_process(pid: Optional[int], create_time: Optional[float]) -> Optional[psutil.Process]:
    """El proceso ``pid`` si sigue vivo y es el mismo (misma hora de creacion); si no, None."""
    if pid is None or create_time is None:
        return None
    try:
        proc = psutil.Process(int(pid))
        if abs(proc.create_time() - float(create_time)) > _CREATE_TIME_TOLERANCE_S:
            return None
        if proc.status() == psutil.STATUS_ZOMBIE:
            return None
        return proc
    except (psutil.Error, ValueError, OSError):
        return None


def _terminate_tree(pid: Optional[int], create_time: Optional[float], timeout: float = 10.0) -> bool:
    """Termina el proceso y todos sus descendientes si sigue siendo el mismo proceso.

    Los hijos se recogen antes de terminar al padre: en Windows terminar el
    padre no cierra a sus hijos.
    """
    root = _same_process(pid, create_time)
    if root is None:
        return False
    try:
        procs: List[psutil.Process] = root.children(recursive=True)
    except psutil.Error:
        procs = []
    procs.append(root)
    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            pass
    _gone, alive = psutil.wait_procs(procs, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=timeout)
    return True


def _remove_quietly(path: Optional[str]) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError as exc:
        logger.debug("[OLLAMA] No se pudo borrar %s: %s", path, exc)


# ============================================================================
# SERVIDOR
# ============================================================================


@dataclass
class OllamaServer:
    """Servidor Ollama en uso: arrancado aqui (``started_by_us``) o ya existente."""

    host: str
    started_by_us: bool
    pid: Optional[int] = None
    create_time: Optional[float] = None
    command: List[str] = field(default_factory=list)
    log_path: Optional[str] = None
    watchdog_pid: Optional[int] = None
    _process: Any = field(default=None, repr=False)
    _log_file: Any = field(default=None, repr=False)
    _watchdog: Any = field(default=None, repr=False)
    _stopped: bool = field(default=False, repr=False)
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    def is_running(self) -> bool:
        """El proceso propio sigue vivo o, si no es propio, el servidor responde."""
        if self.started_by_us:
            return not self._stopped and _same_process(self.pid, self.create_time) is not None
        return server_responds(self.host)

    def stop(self, timeout: float = 10.0) -> bool:
        """Cierra el servidor y sus procesos hijos solo si lo arranco este proceso.

        Devuelve True la primera vez que se cierra un servidor propio; False si
        no es propio (nunca se toca) o ya estaba cerrado.
        """
        with self._lock:
            if not self.started_by_us or self._stopped:
                return False
            self._stopped = True
        if not _terminate_tree(self.pid, self.create_time, timeout):
            # Sin identidad comprobable solo se cierra el proceso lanzado aqui.
            process = self._process
            if process is not None and process.poll() is None:
                try:
                    process.kill()
                except OSError as exc:
                    logger.warning("[OLLAMA] No se pudo cerrar ollama serve (PID %s): %s", self.pid, exc)
        if self._process is not None:
            try:
                self._process.wait(timeout=timeout)
            except Exception as exc:
                logger.warning("[OLLAMA] ollama serve (PID %s) no termino: %s", self.pid, exc)
        self._stop_watchdog(timeout)
        self._close_log(remove=True)
        logger.info("[OLLAMA] Servidor de %s (PID %s) cerrado", self.host, self.pid)
        return True

    def log_tail(self) -> str:
        """Ultimas lineas de la salida de ``ollama serve`` (para diagnosticar un fallo)."""
        if not self.log_path:
            return ""
        try:
            with open(self.log_path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - _LOG_TAIL_CHARS))
                return handle.read().decode("utf-8", "replace").strip()
        except OSError:
            return ""

    def _start_watchdog(self) -> None:
        if self.create_time is None:
            return
        try:
            own_create_time = psutil.Process().create_time()
        except psutil.Error as exc:
            logger.warning("[OLLAMA] Sin vigilante: no se pudo leer el proceso actual: %s", exc)
            return
        argv = [
            sys.executable,
            "-m",
            "src.core.ollama_server",
            "--watch",
            str(os.getpid()),
            repr(own_create_time),
            str(self.pid),
            repr(self.create_time),
        ]
        if self.log_path:
            argv += ["--log", self.log_path]
        try:
            self._watchdog = subprocess.Popen(
                argv,
                cwd=str(_PROJECT_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
                start_new_session=True,
            )
            self.watchdog_pid = self._watchdog.pid
        except OSError as exc:
            logger.warning("[OLLAMA] No se pudo lanzar el vigilante de ollama serve: %s", exc)

    def _stop_watchdog(self, timeout: float) -> None:
        watchdog = self._watchdog
        if watchdog is None:
            return
        if watchdog.poll() is None:
            try:
                watchdog.terminate()
                watchdog.wait(timeout=timeout)
            except Exception as exc:
                logger.warning("[OLLAMA] No se pudo cerrar el vigilante (PID %s): %s", watchdog.pid, exc)

    def _close_log(self, remove: bool) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None
        if remove:
            _remove_quietly(self.log_path)


def _wait_until_ready(url: str, process: subprocess.Popen, timeout: float) -> bool:
    """Espera (sin pausa fija) a que el servidor responda; False si el proceso termina o vence el plazo."""
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        if process.poll() is not None:
            return False
        if server_responds(url, timeout=1.0):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


def ensure_ollama_server(
    host: Optional[str] = None,
    timeout: float = 30.0,
    command: Optional[Sequence[str]] = None,
    watch: bool = True,
    register_atexit: bool = True,
) -> OllamaServer:
    """Devuelve un servidor Ollama que responde, arrancando ``ollama serve`` si hace falta.

    Args:
        host: direccion del servidor; por defecto ``OLLAMA_HOST`` o
            ``http://127.0.0.1:11434``.
        timeout: segundos maximos de espera a que el servidor arrancado responda.
        command: programa que se ejecuta con el argumento ``serve``; por
            defecto, el ejecutable ``ollama`` que encuentra
            ``find_ollama_executable``.
        watch: lanzar el vigilante que cierra el servidor si este proceso
            muere sin limpiar.
        register_atexit: cerrar el servidor al salir del interprete.

    Raises:
        OllamaServerError: la direccion no es local, falta el ejecutable o el
            servidor no responde a tiempo (incluye la salida de ``ollama serve``).
    """
    url = resolve_host(host)
    if server_responds(url):
        logger.info("[OLLAMA] Servidor ya disponible en %s: se reutiliza y no se cerrara", url)
        return OllamaServer(host=url, started_by_us=False)
    if not is_local_host(url):
        raise OllamaServerError("el servidor Ollama %s no responde y no es local: no se arranca" % url)

    base = [str(part) for part in command] if command else []
    if not base:
        executable = find_ollama_executable()
        if executable is None:
            raise OllamaServerError(
                "Ollama no responde en %s y no se encuentra el ejecutable 'ollama'; "
                "instalarlo desde https://ollama.com/download" % url
            )
        base = [executable]
    argv = base + ["serve"]
    env = dict(os.environ)
    env["OLLAMA_HOST"] = _bind_address(url)

    fd, log_path = tempfile.mkstemp(prefix="jarvis_ollama_serve_", suffix=".log")
    log_file = os.fdopen(fd, "wb")
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=_CREATE_NO_WINDOW,
        )
    except OSError as exc:
        log_file.close()
        _remove_quietly(log_path)
        raise OllamaServerError("no se pudo ejecutar %s: %s" % (argv, exc)) from exc

    server = OllamaServer(
        host=url,
        started_by_us=True,
        pid=process.pid,
        command=argv,
        log_path=log_path,
        _process=process,
        _log_file=log_file,
    )
    try:
        server.create_time = psutil.Process(process.pid).create_time()
    except psutil.Error:
        pass  # ya termino: lo detecta la espera

    if not _wait_until_ready(url, process, timeout):
        exited = process.poll() is not None
        output = server.log_tail()
        server.stop(timeout=5.0)
        if exited and server_responds(url):
            # Otro proceso arranco un servidor en la misma direccion a la vez.
            logger.info("[OLLAMA] Otro proceso ya sirve %s: se reutiliza y no se cerrara", url)
            return OllamaServer(host=url, started_by_us=False)
        reason = "termino al arrancar" if exited else "no respondio en %.0f s" % float(timeout)
        raise OllamaServerError("ollama serve %s (%s). Salida: %s" % (reason, url, output or "(vacia)"))

    if watch:
        server._start_watchdog()
    if register_atexit:
        atexit.register(server.stop)
    logger.info("[OLLAMA] ollama serve arrancado en %s (PID %s)", url, process.pid)
    return server


# ============================================================================
# VIGILANTE (proceso aparte)
# ============================================================================


def watch_server(
    parent_pid: int,
    parent_create_time: float,
    server_pid: int,
    server_create_time: float,
    log_path: Optional[str] = None,
    interval: float = _WATCH_INTERVAL_S,
) -> int:
    """Bucle del vigilante: cierra el servidor cuando su creador deja de existir.

    Termina sin hacer nada si el servidor ya no existe (cierre normal).
    """
    while True:
        if _same_process(server_pid, server_create_time) is None:
            return 0
        if _same_process(parent_pid, parent_create_time) is None:
            _terminate_tree(server_pid, server_create_time)
            _remove_quietly(log_path)
            return 0
        time.sleep(interval)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Vigilante del ollama serve arrancado por JARVIS")
    parser.add_argument(
        "--watch",
        nargs=4,
        required=True,
        metavar=("PADRE_PID", "PADRE_INICIO", "SERVIDOR_PID", "SERVIDOR_INICIO"),
    )
    parser.add_argument("--log", default=None)
    parser.add_argument("--interval", type=float, default=_WATCH_INTERVAL_S)
    args = parser.parse_args(argv)
    parent_pid, parent_create_time, server_pid, server_create_time = args.watch
    return watch_server(
        int(parent_pid),
        float(parent_create_time),
        int(server_pid),
        float(server_create_time),
        args.log,
        args.interval,
    )


if __name__ == "__main__":
    sys.exit(_main())
