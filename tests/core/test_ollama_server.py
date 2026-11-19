# -*- coding: ascii -*-
"""
Tests de src/core/ollama_server.py: direccion, ejecutable y ciclo de vida.

Las pruebas de ciclo de vida usan procesos reales con un servidor Ollama falso
(tests/fixtures/ollama_falso/servidor_ollama_falso.py) en un puerto libre:
arranque y espera hasta que responde, reutilizacion de un servidor ajeno sin
cerrarlo, cierre de todo el arbol de procesos (servidor, runner y vigilante),
errores de arranque con la salida del proceso y el vigilante que cierra el
servidor cuando el proceso que lo arranco muere de golpe. No usan ni tocan el
Ollama real del equipo; se ejecutan en cualquier sistema.
"""

import json
import os
import socket
import subprocess
import sys
import textwrap
import time

import psutil
import pytest

import src.core.ollama_server as ollama_server
from src.core.ollama_server import (
    DEFAULT_HOST,
    OllamaServerError,
    ensure_ollama_server,
    find_ollama_executable,
    is_local_host,
    resolve_host,
    server_responds,
)

_TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_TESTS_DIR)
FALSO = os.path.join(_TESTS_DIR, "fixtures", "ollama_falso", "servidor_ollama_falso.py")
COMANDO_FALSO = [sys.executable, FALSO]
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _esperar(condicion, timeout=15.0):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.1)
    return bool(condicion())


def _vivo(proceso):
    try:
        return proceso.is_running() and proceso.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _descendientes_vivos():
    """PIDs de los procesos descendientes de este proceso de pytest que siguen vivos."""
    return {p.pid for p in psutil.Process().children(recursive=True) if _vivo(p)}


def _matar_arbol(pid):
    """Limpieza de seguridad de las pruebas: cierra un proceso y sus hijos si quedan."""
    try:
        raiz = psutil.Process(pid)
        procesos = raiz.children(recursive=True) + [raiz]
    except psutil.Error:
        return
    for proceso in procesos:
        try:
            proceso.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(procesos, timeout=5)


@pytest.fixture
def direccion():
    """Direccion local en un puerto libre: nunca la del Ollama del usuario."""
    return "http://127.0.0.1:%d" % _puerto_libre()


class TestDireccion:
    def test_por_defecto(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        assert resolve_host() == DEFAULT_HOST

    def test_desde_ollama_host_y_explicita(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", ":11555")
        assert resolve_host() == "http://127.0.0.1:11555"
        assert resolve_host("127.0.0.1:11666") == "http://127.0.0.1:11666"

    def test_direcciones_locales_y_remotas(self):
        for url in ("http://127.0.0.1:11434", "http://localhost:1", "http://[::1]:11434",
                    "http://0.0.0.0:11434", "http://127.0.0.2:5"):
            assert is_local_host(url), url
        for url in ("http://198.51.100.1:11434", "https://ollama.example.com:443"):
            assert not is_local_host(url), url

    def test_direccion_de_escucha_y_de_sondeo(self):
        assert ollama_server._bind_address("http://127.0.0.1:11555") == "127.0.0.1:11555"
        assert ollama_server._probe_base("http://0.0.0.0:11434") == "http://127.0.0.1:11434"
        assert ollama_server._probe_base("http://[::]:11434") == "http://[::1]:11434"

    def test_sin_servidor_no_responde(self, direccion):
        assert server_responds(direccion, timeout=0.5) is False


class TestEjecutable:
    def test_usa_el_ejecutable_del_path(self, monkeypatch):
        monkeypatch.setattr(ollama_server.shutil, "which",
                            lambda nombre: "/opt/ollama/bin/ollama" if nombre == "ollama" else None)
        assert find_ollama_executable() == "/opt/ollama/bin/ollama"

    def test_instalacion_por_usuario_si_no_esta_en_el_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ollama_server.shutil, "which", lambda nombre: None)
        ejecutable = tmp_path / "Programs" / "Ollama" / "ollama.exe"
        ejecutable.parent.mkdir(parents=True)
        ejecutable.write_bytes(b"")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert find_ollama_executable() == str(ejecutable)

    def test_sin_ejecutable(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ollama_server.shutil, "which", lambda nombre: None)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert find_ollama_executable() is None

    def test_sin_ejecutable_error_claro_sin_lanzar_procesos(self, monkeypatch, direccion):
        monkeypatch.setattr(ollama_server, "find_ollama_executable", lambda: None)
        antes = _descendientes_vivos()
        with pytest.raises(OllamaServerError, match="ollama.com/download"):
            ensure_ollama_server(host=direccion, timeout=1, register_atexit=False)
        assert _descendientes_vivos() == antes

    def test_direccion_remota_no_arranca_nada(self):
        antes = _descendientes_vivos()
        with pytest.raises(OllamaServerError, match="no es local"):
            ensure_ollama_server(host="http://198.51.100.1:11434", timeout=1, register_atexit=False)
        assert _descendientes_vivos() == antes


class TestCicloDeVidaConServidorFalso:
    def test_arranca_responde_y_cierra_todo_el_arbol(self, direccion):
        servidor = ensure_ollama_server(host=direccion, command=COMANDO_FALSO, timeout=20,
                                        register_atexit=False)
        try:
            assert servidor.started_by_us is True
            assert servidor.host == direccion
            assert servidor.command == COMANDO_FALSO + ["serve"]
            assert server_responds(direccion, timeout=1.0)
            assert servidor.is_running() is True
            raiz = psutil.Process(servidor.pid)
            hijos = raiz.children(recursive=True)
            assert hijos, "el servidor falso debe tener su proceso runner"
            assert servidor.log_path and os.path.exists(servidor.log_path)
            assert servidor.watchdog_pid is not None
            vigilante = psutil.Process(servidor.watchdog_pid)
            assert _vivo(vigilante)
        except BaseException:
            servidor.stop()
            raise
        assert servidor.stop() is True
        assert not server_responds(direccion, timeout=0.5)
        assert not _vivo(raiz)
        assert _esperar(lambda: not any(_vivo(h) for h in hijos), timeout=10)
        assert _esperar(lambda: not _vivo(vigilante), timeout=10)
        assert not os.path.exists(servidor.log_path)
        assert servidor.is_running() is False
        # Idempotente: un segundo cierre no hace nada.
        assert servidor.stop() is False

    def test_reutiliza_un_servidor_ajeno_y_no_lo_cierra(self, direccion):
        entorno = dict(os.environ, OLLAMA_HOST=ollama_server._bind_address(direccion))
        ajeno = subprocess.Popen(COMANDO_FALSO + ["serve"], env=entorno, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=SIN_VENTANA)
        try:
            assert _esperar(lambda: server_responds(direccion, timeout=0.5), timeout=20)
            antes = _descendientes_vivos()
            servidor = ensure_ollama_server(host=direccion, command=COMANDO_FALSO, register_atexit=False)
            assert servidor.started_by_us is False
            assert servidor.pid is None
            # No se lanzo ningun servidor ni vigilante propio.
            assert _descendientes_vivos() == antes
            assert servidor.is_running() is True
            assert servidor.stop() is False
            assert server_responds(direccion, timeout=1.0)
            assert ajeno.poll() is None
        finally:
            _matar_arbol(ajeno.pid)
            ajeno.wait(timeout=10)

    def test_proceso_que_termina_al_arrancar_da_error_con_su_salida(self, direccion, monkeypatch):
        monkeypatch.setenv("OLLAMA_FALSO_MODO", "fallo")
        antes = _descendientes_vivos()
        with pytest.raises(OllamaServerError) as error:
            ensure_ollama_server(host=direccion, command=COMANDO_FALSO, timeout=20, register_atexit=False)
        assert "termino al arrancar" in str(error.value)
        assert "address already in use" in str(error.value)
        assert _esperar(lambda: _descendientes_vivos() == antes, timeout=10)

    def test_servidor_que_no_responde_se_cierra_al_vencer_el_plazo(self, direccion, monkeypatch):
        monkeypatch.setenv("OLLAMA_FALSO_MODO", "mudo")
        antes = _descendientes_vivos()
        inicio = time.monotonic()
        with pytest.raises(OllamaServerError, match="no respondio en 2 s"):
            ensure_ollama_server(host=direccion, command=COMANDO_FALSO, timeout=2, register_atexit=False)
        assert time.monotonic() - inicio < 20
        # El servidor mudo y su runner quedan cerrados.
        assert _esperar(lambda: _descendientes_vivos() == antes, timeout=10)


class TestVigilante:
    def test_cierra_el_servidor_si_el_proceso_que_lo_arranco_muere_de_golpe(self, direccion, tmp_path):
        guion = tmp_path / "proceso_padre.py"
        guion.write_text(textwrap.dedent("""
            import json, sys, time
            sys.path.insert(0, %r)
            from src.core.ollama_server import ensure_ollama_server
            servidor = ensure_ollama_server(host=%r, command=%r, timeout=20, register_atexit=False)
            print(json.dumps({"servidor": servidor.pid, "vigilante": servidor.watchdog_pid}), flush=True)
            time.sleep(600)
        """) % (_RAIZ, direccion, COMANDO_FALSO), encoding="utf-8")
        padre = subprocess.Popen([sys.executable, str(guion)], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 creationflags=SIN_VENTANA)
        info = {}
        try:
            linea = padre.stdout.readline()
            try:
                info = json.loads(linea)
            except ValueError:
                pytest.fail("el proceso padre no arranco el servidor: %s%s" % (linea, padre.stdout.read()))
            servidor = psutil.Process(info["servidor"])
            hijos = servidor.children(recursive=True)
            vigilante = psutil.Process(info["vigilante"])
            assert server_responds(direccion, timeout=1.0)

            # Muerte brusca: no se ejecutan atexit ni stop() en el proceso padre.
            padre.kill()
            padre.wait(timeout=10)

            assert _esperar(lambda: not _vivo(servidor), timeout=20), "el vigilante no cerro el servidor"
            assert _esperar(lambda: not any(_vivo(h) for h in hijos), timeout=10)
            assert _esperar(lambda: not _vivo(vigilante), timeout=10)
            assert not server_responds(direccion, timeout=0.5)
        finally:
            if padre.poll() is None:
                padre.kill()
                padre.wait(timeout=10)
            padre.stdout.close()
            for pid in (info.get("servidor"), info.get("vigilante")):
                if pid:
                    _matar_arbol(pid)
