"""
Tests de contrato del observador opcional de cambios del sistema de archivos
(unidad 3.8.5.1.4.5.7).

Verifican que el observador es una optimizacion opcional: reporta no disponible
cuando `watchdog` no esta instalado, degrada de forma segura sin fallar el
sistema, nunca toca la base de datos del inventario y su contrato de eventos
es el esperado. Cuando `watchdog` no esta instalado (entorno actual), el
camino real que se ejecuta es el de no disponibilidad; el camino con
observador activo se simula mediante sustitucion de los componentes de
watchdog para verificar el contrato de traduccion de eventos sin depender del
paquete externo.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import src.hands.filesystem_observer as fobs
from src.hands.filesystem_observer import (
    FileSystemChangeEvent,
    FileSystemObserver,
    ObserverUnavailableError,
    _ChangeHandler,
)


# ---------------------------------------------------------------------------
# Simuladores de watchdog (sustituyen al paquete ausente solo en los tests de
# camino disponible; no se instalan ni se requieren en produccion).
# ---------------------------------------------------------------------------

class _FakeEvent:
    def __init__(self, src_path: str, dest_path: str | None = None, is_directory: bool = False) -> None:
        self.src_path = src_path
        self.dest_path = dest_path
        self.is_directory = is_directory


class _FakeEventHandler:
    def __init__(self) -> None:
        pass


class _FakeObserver:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.joined = False
        self.scheduled: list[tuple] = []

    def schedule(self, handler, path: str, recursive: bool = True) -> None:
        self.scheduled.append((handler, path, recursive))

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def join(self) -> None:
        self.joined = True


def _simular_watchdog_disponible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fobs, "_WATCHDOG_AVAILABLE", True)
    monkeypatch.setattr(fobs, "_WatchdogObserver", _FakeObserver)
    monkeypatch.setattr(fobs, "_WatchdogEventHandler", _FakeEventHandler)


# ---------------------------------------------------------------------------
# No disponibilidad (camino real del entorno actual: watchdog no instalado).
# ---------------------------------------------------------------------------

def test_observador_reporta_no_disponible_sin_watchdog():
    """En el entorno actual watchdog no esta instalado, por lo que
    is_available() debe ser False y el observador degrada de forma segura."""
    assert FileSystemObserver.is_available() is False


def test_observador_sin_watchdog_no_puede_iniciarse_levanta_error():
    """start() levanta ObserverUnavailableError cuando watchdog no esta
    disponible, sin dejar el observador en ejecucion."""
    observador = FileSystemObserver(lambda evento: None)
    assert observador.is_running is False
    with pytest.raises(ObserverUnavailableError):
        observador.start("C:/Carpeta/Observada")
    assert observador.is_running is False


def test_error_menciona_refresco_bajo_demanda_como_alternativa():
    """El error de no disponibilidad orienta al refresco bajo demanda, que no
    depende de observadores (3.8.5.1.4.5.6)."""
    observador = FileSystemObserver(lambda evento: None)
    with pytest.raises(ObserverUnavailableError) as exc:
        observador.start("C:/Carpeta/Observada")
    mensaje = str(exc.value).lower()
    assert "refrescar_entrada_por_ruta" in mensaje or "refresco bajo demanda" in mensaje


def test_detener_sin_iniciar_no_falla_y_no_esta_ejecutando():
    """stop() es seguro llamar antes de start() y varias veces."""
    observador = FileSystemObserver(lambda evento: None)
    observador.stop()
    observador.stop()
    assert observador.is_running is False


def test_callback_debe_ser_invocable():
    """El constructor rechaza un callback que no sea invocable."""
    with pytest.raises(TypeError):
        FileSystemObserver("no soy invocable")  # type: ignore[arg-type]


def test_observador_no_acopla_al_inventario():
    """Separacion de responsabilidades: el modulo del observador no importa
    ni referencia system_inventory_storage, ni toca la base de datos."""
    import src.hands.filesystem_observer as modulo

    fuente = modulo.__file__
    assert "filesystem_observer" in Path(fuente).name
    codigo = Path(fuente).read_text(encoding="utf-8")
    lineas_import = [
        linea
        for linea in codigo.splitlines()
        if linea.lstrip().startswith(("import ", "from "))
    ]
    # El observador no importa ni acopla el almacenamiento del inventario.
    assert not any("system_inventory_storage" in linea for linea in lineas_import)
    assert not any("sqlite3" in linea for linea in lineas_import)


def test_evento_tiene_campos_esperados():
    """FileSystemChangeEvent tiene los campos del contrato y es inmutable."""
    evento = FileSystemChangeEvent(
        event_type="created",
        path="C:/Carpeta/archivo.txt",
        timestamp="2026-11-10T10:00:00+00:00",
    )
    assert evento.event_type == "created"
    assert evento.path == "C:/Carpeta/archivo.txt"
    assert evento.timestamp == "2026-11-10T10:00:00+00:00"
    with pytest.raises(FrozenInstanceError):
        evento.event_type = "modificado"


# ---------------------------------------------------------------------------
# Camino disponible (simulado): contrato de inicio, detencion y traduccion
# de eventos sin depender del paquete watchdog real.
# ---------------------------------------------------------------------------

def test_start_con_simulador_inicia_y_registra_ruta(monkeypatch: pytest.MonkeyPatch):
    """Con watchdog simulado disponible, start() inicia el observador y
    programa la ruta dada."""
    _simular_watchdog_disponible(monkeypatch)
    eventos = []
    observador = FileSystemObserver(lambda e: eventos.append(e))
    observador.start("C:/Carpeta/Observada", recursive=True)

    assert observador.is_running is True
    assert len(observador._observer.scheduled) == 1  # type: ignore[attr-defined]
    handler, ruta, recursive = observador._observer.scheduled[0]  # type: ignore[attr-defined]
    assert ruta.replace("\\", "/") == "C:/Carpeta/Observada"
    assert recursive is True
    # El handler programado traduce eventos al callback del observador.
    handler.on_created(_FakeEvent("C:/Carpeta/x.txt"))
    assert len(eventos) == 1
    assert eventos[0].path == "C:/Carpeta/x.txt"
    assert eventos[0].event_type == "created"

    falso_observer = observador._observer  # type: ignore[attr-defined]
    observador.stop()
    assert observador.is_running is False
    assert observador._observer is None
    assert falso_observer.stopped is True  # type: ignore[attr-defined]
    assert falso_observer.joined is True  # type: ignore[attr-defined]


def test_handler_traduce_eventos_a_FileSystemChangeEvent(monkeypatch: pytest.MonkeyPatch):
    """El handler traduce created/modified/deleted/moved a eventos con los
    campos esperados y los entrega al callback."""
    _simular_watchdog_disponible(monkeypatch)
    eventos = []
    observador = FileSystemObserver(lambda e: eventos.append(e))
    handler = _ChangeHandler(observador._callback)

    handler.on_created(_FakeEvent("C:/Carpeta/a.txt"))
    handler.on_modified(_FakeEvent("C:/Carpeta/b.txt"))
    handler.on_deleted(_FakeEvent("C:/Carpeta/c.txt"))
    handler.on_moved(_FakeEvent("C:/Carpeta/viejo.txt", dest_path="C:/Carpeta/nuevo.txt"))

    assert len(eventos) == 4
    assert eventos[0].event_type == "created"
    assert eventos[0].path == "C:/Carpeta/a.txt"
    assert eventos[1].event_type == "modified"
    assert eventos[1].path == "C:/Carpeta/b.txt"
    assert eventos[2].event_type == "deleted"
    assert eventos[2].path == "C:/Carpeta/c.txt"
    assert eventos[3].event_type == "moved"
    assert eventos[3].path == "C:/Carpeta/nuevo.txt"
    for evento in eventos:
        assert evento.timestamp  # ISO 8601 no vacio
