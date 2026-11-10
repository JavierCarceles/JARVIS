"""
Observador opcional de cambios del sistema de archivos (unidad 3.8.5.1.4.5.7).

Este modulo implementa una OPTIMIZACION OPCIONAL de notificaciones de cambios
del sistema de archivos. Nunca sustituye al escaneo basado en almacenamiento
(3.8.5.1.4.4/4.5) ni al refresco bajo demanda (3.8.5.1.4.5.6): los
observadores pueden perder eventos y tienen limites por plataforma, por lo que
el inventario sigue siendo fuente de verdad mediante escaneos y
revalidaciones puntuales (`refrescar_entrada_por_ruta`,
`refrescar_volumen`, `revalidar_destino_aplicacion`).

Se prefiere `watchdog` cuando esta disponible; si no lo esta, el observador
reporta no disponible y degrada de forma segura sin fallar el sistema. No toca
la base de datos del inventario: separacion de responsabilidades con
`system_inventory_storage`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

try:
    from watchdog.observers import Observer as _WatchdogObserver
    from watchdog.events import FileSystemEventHandler as _WatchdogEventHandler

    _WATCHDOG_AVAILABLE = True
except ImportError:  # watchdog no instalado: optimizacion opcional ausente
    _WatchdogObserver = None  # type: ignore[assignment]
    _WatchdogEventHandler = None  # type: ignore[assignment]
    _WATCHDOG_AVAILABLE = False


class ObserverUnavailableError(Exception):
    """El observador de sistema de archivos no esta disponible en este entorno.

    Se levanta al intentar iniciar el observador cuando `watchdog` no esta
    instalado. No es un fallo del inventario: el consumidor puede seguir usando
    refresco bajo demanda, que no depende de observadores.
    """


@dataclass(frozen=True)
class FileSystemChangeEvent:
    """Evento de cambio del sistema de archivos observado (hecho, no inferencia).

    `event_type` es uno de: "created", "modified", "deleted", "moved".
    Para eventos "moved", `path` es la ruta destino. `timestamp` es ISO 8601 UTC.
    """

    event_type: str
    path: str
    timestamp: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _ChangeHandler:
    """Traduce eventos de watchdog (o de un simulador de test) a
    `FileSystemChangeEvent` e invoca el callback del consumidor."""

    def __init__(self, callback: Callable[[FileSystemChangeEvent], None]) -> None:
        self._callback = callback

    def _emit(self, event_type: str, path: str) -> None:
        self._callback(
            FileSystemChangeEvent(event_type=event_type, path=path, timestamp=_now_iso())
        )

    # Eventos de watchdog.
    def on_created(self, event) -> None:
        self._emit("created", getattr(event, "src_path", str(event)))

    def on_modified(self, event) -> None:
        self._emit("modified", getattr(event, "src_path", str(event)))

    def on_deleted(self, event) -> None:
        self._emit("deleted", getattr(event, "src_path", str(event)))

    def on_moved(self, event) -> None:
        dest = getattr(event, "dest_path", None)
        self._emit("moved", dest if dest else getattr(event, "src_path", str(event)))


class FileSystemObserver:
    """Observador opcional de cambios del sistema de archivos.

    Constructor:
        `callback` invocable que recibe un `FileSystemChangeEvent` por cada
        cambio detectado.

    Flujo:
        1. `is_available()` indica si `watchdog` esta instalado.
        2. `start(path, recursive=True)` inicia la observacion; levanta
           `ObserverUnavailableError` si `watchdog` no esta disponible.
        3. `stop()` detiene la observacion y libera recursos.
        4. `is_running()` indica si esta observando activamente.

    El observador no modifica el inventario ni marca entradas como eliminadas;
    solo notifica cambios para que el consumidor decida si revalida mediante
    refresco bajo demanda (3.8.5.1.4.5.6).
    """

    def __init__(self, callback: Callable[[FileSystemChangeEvent], None]) -> None:
        if not callable(callback):
            raise TypeError("callback debe ser invocable")
        self._callback = callback
        self._observer: Optional[_WatchdogObserver] = None
        self._handler: Optional[_ChangeHandler] = None
        self._watched_path: Optional[str] = None
        self._running = False

    # ------------------------------------------------------------------ #
    # Disponibilidad
    # ------------------------------------------------------------------ #
    @classmethod
    def is_available(cls) -> bool:
        """Devuelve True si `watchdog` esta instalado y el observador usable."""
        return _WATCHDOG_AVAILABLE

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        """True mientras el observador este iniciado y no detenido."""
        return self._running

    def start(self, path: str, recursive: bool = True) -> None:
        """Inicia la observacion de `path`.

        Requiere `watchdog` instalado. Si ya esta en ejecucion, no hace nada.
        """
        if not _WATCHDOG_AVAILABLE:
            raise ObserverUnavailableError(
                "watchdog no esta instalado; el observador de sistema de "
                "archivos es una optimizacion opcional no disponible en este "
                "entorno. Use refresco bajo demanda ("
                "refrescar_entrada_por_ruta / refrescar_volumen / "
                "revalidar_destino_aplicacion de system_inventory_storage) en "
                "su lugar, que no depende de observadores."
            )
        if self._running:
            return
        if not path or not isinstance(path, str):
            raise ValueError("path debe ser una ruta no vacia.")
        ruta = os.path.abspath(path)

        self._handler = _ChangeHandler(self._callback)
        watchdog_handler = _WatchdogEventHandler()
        # Copiar los metodos de traduccion al handler de watchdog.
        watchdog_handler.on_created = self._handler.on_created  # type: ignore[assignment]
        watchdog_handler.on_modified = self._handler.on_modified  # type: ignore[assignment]
        watchdog_handler.on_deleted = self._handler.on_deleted  # type: ignore[assignment]
        watchdog_handler.on_moved = self._handler.on_moved  # type: ignore[assignment]

        self._observer = _WatchdogObserver()  # type: ignore[call-arg]
        self._observer.schedule(watchdog_handler, ruta, recursive=recursive)
        self._observer.start()
        self._watched_path = ruta
        self._running = True

    def stop(self) -> None:
        """Detiene la observacion. Es seguro llamar varias veces o antes de
        start()."""
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join()
            except Exception:
                # No dejar el observador colgado ni ocultar el estado: se
                # marca como detenido aunque la detencion subyacente falle.
                pass
            self._observer = None
        self._handler = None
        self._watched_path = None
        self._running = False
