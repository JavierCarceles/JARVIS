"""
Carga perezosa de modulos y bibliotecas nativas dependientes del SO.

Permite que cualquier modulo del proyecto se importe sin error en Windows y en
macOS aunque use, en algunas de sus funciones, APIs que solo existen en un
sistema (``ctypes.windll``, ``pywinauto``, ``pygetwindow``, ``winsound``...).

El modulo nativo solo se importa la primera vez que se accede a uno de sus
atributos. Si el SO no lo ofrece o la dependencia no esta instalada, el acceso
levanta ``NativeDependencyUnavailable`` con un mensaje explicito, en lugar de
fallar al importar el modulo consumidor.

Uso:

    from src.desktop.native_imports import lazy_module, lazy_windll

    gw = lazy_module("pygetwindow")
    USER32 = lazy_windll("user32")

    USER32.IsWindow(hwnd)          # importa/carga solo aqui
"""

from __future__ import annotations

import importlib
import sys
import threading
from typing import Any, Optional

__all__ = [
    "NativeDependencyUnavailable",
    "LazyModule",
    "LazyWinDLL",
    "lazy_module",
    "lazy_windll",
    "is_windows",
    "is_macos",
    "current_platform_name",
]


class NativeDependencyUnavailable(ImportError):
    """Una dependencia nativa no esta disponible en este SO o entorno."""


def is_windows() -> bool:
    """True si el proceso se ejecuta en Windows."""
    return sys.platform == "win32"


def is_macos() -> bool:
    """True si el proceso se ejecuta en macOS."""
    return sys.platform == "darwin"


def current_platform_name() -> str:
    """Nombre normalizado del SO actual: ``windows``, ``macos`` u ``otro``."""
    if is_windows():
        return "windows"
    if is_macos():
        return "macos"
    return "otro"


class LazyModule:
    """Proxy que importa un modulo la primera vez que se usa un atributo.

    Argumentos:
        module_name: nombre importable del modulo (``"pygetwindow"``).
        required_platform: ``"win32"``/``"darwin"`` si el modulo solo tiene
            sentido en un SO; en otro SO el acceso falla con un error claro sin
            intentar importarlo.
    """

    def __init__(self, module_name: str, required_platform: Optional[str] = None) -> None:
        object.__setattr__(self, "_module_name", module_name)
        object.__setattr__(self, "_required_platform", required_platform)
        object.__setattr__(self, "_module", None)
        object.__setattr__(self, "_error", None)
        object.__setattr__(self, "_lock", threading.Lock())

    def _load(self) -> Any:
        module = object.__getattribute__(self, "_module")
        if module is not None:
            return module
        lock = object.__getattribute__(self, "_lock")
        with lock:
            module = object.__getattribute__(self, "_module")
            if module is not None:
                return module
            name = object.__getattribute__(self, "_module_name")
            required = object.__getattribute__(self, "_required_platform")
            if required and sys.platform != required:
                raise NativeDependencyUnavailable(
                    "El modulo nativo %s solo esta disponible en %s (SO actual: %s)"
                    % (name, required, sys.platform)
                )
            try:
                module = importlib.import_module(name)
            except Exception as exc:  # ImportError, NotImplementedError, OSError...
                object.__setattr__(self, "_error", exc)
                raise NativeDependencyUnavailable(
                    "No se pudo importar el modulo nativo %s: %s" % (name, exc)
                ) from exc
            object.__setattr__(self, "_module", module)
            return module

    def is_available(self) -> bool:
        """Intenta cargar el modulo y devuelve si esta disponible."""
        try:
            self._load()
            return True
        except NativeDependencyUnavailable:
            return False

    def __getattr__(self, item: str) -> Any:
        return getattr(self._load(), item)

    def __setattr__(self, key: str, value: Any) -> None:
        setattr(self._load(), key, value)

    def __repr__(self) -> str:
        name = object.__getattribute__(self, "_module_name")
        loaded = object.__getattribute__(self, "_module") is not None
        return "<LazyModule %s loaded=%s>" % (name, loaded)


class LazyWinDLL:
    """Proxy de ``ctypes.windll.<dll>`` que solo se resuelve en Windows.

    Mantiene la semantica de ``ctypes.WinDLL``: los atributos devueltos son los
    mismos punteros a funcion cacheados por ctypes, por lo que asignar
    ``argtypes``/``restype`` sobre ellos funciona igual que con el objeto real.
    """

    def __init__(self, dll_name: str) -> None:
        object.__setattr__(self, "_dll_name", dll_name)
        object.__setattr__(self, "_dll", None)

    def _load(self) -> Any:
        dll = object.__getattribute__(self, "_dll")
        if dll is not None:
            return dll
        name = object.__getattribute__(self, "_dll_name")
        if sys.platform != "win32":
            raise NativeDependencyUnavailable(
                "La biblioteca Win32 %s solo existe en Windows (SO actual: %s)"
                % (name, sys.platform)
            )
        import ctypes

        dll = getattr(ctypes.windll, name)
        object.__setattr__(self, "_dll", dll)
        return dll

    def is_available(self) -> bool:
        try:
            self._load()
            return True
        except Exception:
            return False

    def __getattr__(self, item: str) -> Any:
        return getattr(self._load(), item)

    def __setattr__(self, key: str, value: Any) -> None:
        setattr(self._load(), key, value)

    def __repr__(self) -> str:
        name = object.__getattribute__(self, "_dll_name")
        return "<LazyWinDLL %s>" % name


def lazy_module(module_name: str, required_platform: Optional[str] = None) -> LazyModule:
    """Devuelve un proxy perezoso del modulo indicado."""
    return LazyModule(module_name, required_platform=required_platform)


def lazy_windll(dll_name: str) -> LazyWinDLL:
    """Devuelve un proxy perezoso de ``ctypes.windll.<dll_name>``."""
    return LazyWinDLL(dll_name)
