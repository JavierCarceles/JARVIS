"""
Funciones especificas para Google Chrome.

Este modulo contiene unicamente acciones especificas de Chrome.
La logica universal de calibracion, deteccion de aplicaciones y geometria de
monitores pertenece a CalibrationManager y ScreenManager respectivamente.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
import webbrowser
from typing import List, Optional, Any

import sys as _sys

from src.desktop.native_imports import lazy_module as _lazy_module, lazy_windll as _lazy_windll

if _sys.platform == "win32":
    import pyautogui
else:
    pyautogui = _lazy_module("pyautogui")  # import perezoso fuera de Windows

from src.hands.actions.action_registry import ActionType, register_action
from src.core.log import get_logger
from src.desktop.screen_manager import get_screen_manager

logger = get_logger(__name__)


# ============================================================================
# APERTURA DE CHROME
# ============================================================================


@register_action(
    name="abrir_chrome",
    description="Abre Google Chrome en la pantalla predeterminada",
    action_type=ActionType.APPLICATION,
    parameters={},
    confidence_threshold=0.9,
)
def abrir_chrome() -> str:
    """Abre especificamente Google Chrome, sin depender del navegador predeterminado."""
    logger.info("[CHROME] Abriendo Chrome...")
    try:
        if not _abrir_chrome_desde_ruta():
            return "No se pudo abrir Google Chrome."

        logger.info("[CHROME] Chrome abierto exitosamente")
        return "He abierto Google Chrome en tu pantalla predeterminada."
    except Exception as exc:
        logger.error(f"[CHROME] Error al abrir Chrome: {exc}")
        return f"Error al abrir Chrome: {exc}"


@register_action(
    name="abrir_chrome_pantalla",
    description="Abre Google Chrome en una pantalla espec\u00edfica",
    action_type=ActionType.APPLICATION,
    parameters={
        "pantalla": {
            "type": "int",
            "description": "N\u00famero de pantalla disponible",
            "required": True,
        }
    },
    confidence_threshold=0.9,
)
def abrir_chrome_pantalla(pantalla: int = 1) -> str:
    """Abre Chrome en un monitor especifico."""
    try:
        if pantalla < 1:
            return "Error: el n\u00famero de pantalla debe ser mayor que 0."

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla)

        if monitor is None:
            total_monitores = len(getattr(screen_manager, "monitors", []) or [])
            return (
                f"Error: la pantalla {pantalla} no existe. "
                f"Hay {total_monitores} pantalla(s) detectada(s)."
            )

        open_method = getattr(screen_manager, "open_chrome_on_monitor", None)
        if not callable(open_method):
            return "Error: ScreenManager no dispone de apertura de Chrome por monitor."

        if open_method(pantalla):
            return f"He abierto Google Chrome en tu pantalla {pantalla}."

        return f"No se pudo abrir Chrome en pantalla {pantalla}."
    except Exception as exc:
        logger.debug("abrir_chrome_pantalla: %s", exc)
        return f"Error al abrir Chrome en pantalla {pantalla}: {exc}"


# ============================================================================
# CIERRE EXPLICITO
# ============================================================================


@register_action(
    name="cerrar_chrome",
    description="Cierra todas las ventanas de Google Chrome",
    action_type=ActionType.APPLICATION,
    parameters={},
    confidence_threshold=0.9,
)
def cerrar_chrome() -> str:
    """Cierra las ventanas de Google Chrome."""
    logger.info(r"[CHROME] Cerrando Chrome...")
    try:
        screen_manager = get_screen_manager()
        close_method = getattr(screen_manager, "close_chrome", None)
        if not callable(close_method):
            return "Error: ScreenManager no dispone de cierre de Chrome."

        if close_method():
            logger.info(r"[CHROME] Chrome cerrado exitosamente")
            return "He cerrado todas las ventanas de Google Chrome."

        logger.warning(r"[CHROME] No se encontraron ventanas de Chrome para cerrar")
        return "No se encontraron ventanas de Chrome abiertas."
    except Exception as exc:
        logger.debug("cerrar_chrome: %s", exc)
        return f"Error al cerrar Chrome: {exc}"


# ============================================================================
# CALIBRACION ESPECIFICA DE CHROME
# ============================================================================


@register_action(
    name="calibrar_chrome",
    description=(
        "Calibra elementos de Google Chrome usando visi\u00f3n artificial; "
        "0 selecciona autom\u00e1ticamente el monitor adecuado"
    ),
    action_type=ActionType.CALIBRATION,
    parameters={
        "pantalla": {
            "type": "int",
            "description": "N\u00famero de pantalla a calibrar; 0 = selecci\u00f3n autom\u00e1tica",
            "required": False,
        }
    },
    confidence_threshold=0.8,
)
def calibrar_chrome(pantalla: int = 0) -> str:
    """Calibra Chrome usando el flujo universal de aplicaciones.

    La preparacion de ventana, restauracion de minimizadas, maximizacion,
    deteccion de monitor, captura y analisis visual son exactamente las mismas
    que para cualquier otra aplicacion.
    """
    try:
        if pantalla < 0:
            return "Error: el n\u00famero de pantalla no puede ser negativo."

        from src.hands.calibration.calibration_manager import get_calibration_manager

        manager = get_calibration_manager()
        requested = None if int(pantalla) == 0 else int(pantalla)
        result = manager.calibrate_application("chrome", requested)

        if result.success:
            monitor = int(result.screen_number or 0)
            count = int(result.elements_count or 0)
            if monitor > 0:
                return (
                    "Calibraci\u00f3n de Chrome completada en pantalla "
                    f"{monitor}. Detectados {count} elementos."
                )
            return f"Calibraci\u00f3n de Chrome completada. Detectados {count} elementos."

        return f"Error en calibraci\u00f3n: {result.error or 'Error desconocido'}"
    except Exception as exc:
        logger.debug("calibrar_chrome: %s", exc)
        return f"Error al calibrar Chrome: {exc}"


# ============================================================================
# MOVIMIENTO
# ============================================================================


@register_action(
    name="mover_chrome_pantalla",
    description="Mueve la ventana de Chrome a una pantalla espec\u00edfica",
    action_type=ActionType.NAVIGATION,
    parameters={
        "pantalla": {
            "type": "int",
            "description": "N\u00famero de pantalla disponible",
            "required": True,
        }
    },
    confidence_threshold=0.9,
)
def mover_chrome_pantalla(pantalla: int) -> str:
    """Mueve una ventana de Chrome al monitor solicitado."""
    try:
        if pantalla < 1:
            return "Error: el n\u00famero de pantalla debe ser mayor que 0."

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla)

        if monitor is None:
            total_monitores = len(getattr(screen_manager, "monitors", []) or [])
            return (
                f"Error: la pantalla {pantalla} no existe. "
                f"Hay {total_monitores} pantalla(s) detectada(s)."
            )

        chrome_windows = _get_chrome_windows(screen_manager)
        if not chrome_windows:
            return "No se encontr\u00f3 ninguna ventana de Chrome para mover."

        move_method = getattr(screen_manager, "move_window_to_monitor", None)
        if not callable(move_method):
            return "Error: ScreenManager no dispone de movimiento de ventanas entre monitores."

        window = _select_preferred_chrome_window(screen_manager, chrome_windows)

        # Preferir HWND/objeto de ventana cuando ScreenManager lo soporte.
        try:
            moved = bool(move_method(window, pantalla))
        except Exception:
            # Compatibilidad con la API historica basada en titulo.
            moved = bool(move_method("Google", pantalla))

        if moved:
            return f"He movido Google Chrome a tu pantalla {pantalla}."

        return f"No se pudo mover Chrome a pantalla {pantalla}."
    except Exception as exc:
        logger.debug("mover_chrome_pantalla: %s", exc)
        return f"Error al mover Chrome: {exc}"


# ============================================================================
# MAXIMIZAR
# ============================================================================


@register_action(
    name="maximizar_chrome",
    description="Maximiza la ventana de Chrome",
    action_type=ActionType.NAVIGATION,
    parameters={},
    confidence_threshold=0.9,
)
def maximizar_chrome() -> str:
    """Maximiza la ventana de Chrome preferentemente la que esta en primer plano."""
    logger.info(r"[CHROME] Maximizando Chrome...")
    try:
        screen_manager = get_screen_manager()
        chrome_windows = _get_chrome_windows(screen_manager)

        if not chrome_windows:
            logger.warning(r"[CHROME] No se encontro ventana de Chrome para maximizar")
            return "No se encontr\u00f3 ventana de Chrome para maximizar."

        win = _select_preferred_chrome_window(screen_manager, chrome_windows)

        maximize = getattr(win, "maximize", None)
        if not callable(maximize):
            return "No se pudo maximizar la ventana de Chrome."

        maximize()
        time.sleep(1)
        logger.info(r"[CHROME] Chrome maximizado exitosamente")
        return "He maximizado la ventana de Google Chrome."
    except Exception as exc:
        logger.debug("maximizar_chrome: %s", exc)
        return f"Error al maximizar Chrome: {exc}"


# ============================================================================
# FUNCIONES INTERNAS
# ============================================================================


def _get_chrome_executable() -> Optional[str]:
    """Busca chrome.exe en ubicaciones habituales de Windows."""
    routes = [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
    ]

    seen: set[str] = set()
    for route in routes:
        expanded = os.path.expandvars(route)
        if expanded in seen:
            continue
        seen.add(expanded)
        if os.path.isfile(expanded):
            return expanded

    return None


def _abrir_chrome_desde_ruta() -> bool:
    """Abre Chrome directamente; solo usa webbrowser como ultimo fallback."""
    try:
        chrome_exe = _get_chrome_executable()
        if chrome_exe:
            subprocess.Popen([chrome_exe, "https://www.google.com"])
            time.sleep(2)
            return True

        # Algunos sistemas tienen chrome.exe resoluble por PATH.
        try:
            subprocess.Popen(["chrome", "https://www.google.com"])
            time.sleep(2)
            return True
        except (FileNotFoundError, OSError):
            pass

        return bool(webbrowser.open("https://www.google.com"))
    except Exception as exc:
        logger.debug("_abrir_chrome_desde_ruta: %s", exc)
        return False


def _get_chrome_windows(screen_manager: Any) -> List[Any]:
    """Obtiene ventanas de Chrome mediante ScreenManager, si esta disponible."""
    method = getattr(screen_manager, "get_chrome_windows", None)
    if not callable(method):
        return []

    try:
        result = method()
        return list(result or [])
    except Exception as exc:
        logger.debug("_get_chrome_windows: %s", exc)
        return []


def _select_preferred_chrome_window(
    screen_manager: Any,
    chrome_windows: List[Any],
) -> Any:
    """Selecciona la ventana Chrome en primer plano cuando sea posible."""
    foreground_method = getattr(screen_manager, "get_foreground_window", None)
    chrome_check = getattr(screen_manager, "_is_chrome_window", None)

    if callable(foreground_method) and callable(chrome_check):
        try:
            foreground = foreground_method()
            if foreground is not None and chrome_check(foreground):
                return foreground
        except Exception:
            pass

    return chrome_windows[0]


def _verificar_chrome_abierto() -> bool:
    """Verifica si existe al menos una ventana visible de Chrome."""
    try:
        screen_manager = get_screen_manager()
        for win in _get_chrome_windows(screen_manager):
            try:
                visible = getattr(win, "is_visible", True)
                if callable(visible):
                    visible = visible()
                if visible is False:
                    continue
                logger.debug(r"[CHROME] Chrome detectado y visible")
                return True
            except Exception:
                continue

        logger.debug(r"[CHROME] Chrome no detectado entre ventanas abiertas")
        return False
    except Exception as exc:
        logger.debug("_verificar_chrome_abierto: %s", exc)
        return False


def _verificar_chrome_instalado() -> bool:
    """Verifica si Chrome esta instalado o resoluble en el sistema."""
    try:
        if _get_chrome_executable():
            return True

        try:
            result = subprocess.run(
                ["chrome", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return False
    except Exception as exc:
        logger.debug("_verificar_chrome_instalado: %s", exc)
        return False


def _capturar_chrome() -> Optional[str]:
    """
    Captura una ventana de Chrome.

    API legacy. El flujo universal de calibracion captura el monitor completo
    mediante ScreenManager y no depende de esta funcion.
    """
    try:
        screen_manager = get_screen_manager()
        chrome_windows = _get_chrome_windows(screen_manager)
        if not chrome_windows:
            logger.warning(r"[CHROME] No se encontro ventana de Chrome para capturar")
            return None

        win = _select_preferred_chrome_window(screen_manager, chrome_windows)
        left = int(getattr(win, "left", 0))
        top = int(getattr(win, "top", 0))
        width = int(getattr(win, "width", 0))
        height = int(getattr(win, "height", 0))

        if width <= 0 or height <= 0:
            return None

        screenshot = pyautogui.screenshot(region=(left, top, width, height))

        project_root = getattr(screen_manager, "project_root", None)
        if project_root is None:
            project_root = os.getcwd()

        temp_path = Path(project_root) / f"temp_chrome_{int(time.time() * 1000)}.png"
        screenshot.save(temp_path)
        return str(temp_path)
    except Exception as exc:
        logger.debug("_capturar_chrome: %s", exc)
        return None


# ============================================================================
# COMANDOS
# ============================================================================


def get_chrome_commands() -> List[str]:
    """Obtiene los comandos especificos de Chrome."""
    return [
        "abrir_chrome",
        "abrir_chrome_pantalla",
        "cerrar_chrome",
        "calibrar_chrome",
        "mover_chrome_pantalla",
        "maximizar_chrome",
    ]


def get_chrome_action_commands() -> List[str]:
    """Escanea el modulo y devuelve las funciones registradas como acciones."""
    import inspect

    frame = inspect.currentframe()
    try:
        module = inspect.getmodule(frame)
        if module is None:
            return []

        functions = inspect.getmembers(module, inspect.isfunction)
        action_commands: List[str] = []
        for name, func in functions:
            if hasattr(func, "_jarvis_action_info") or hasattr(func, "_action_info"):
                action_commands.append(name)
        return action_commands
    finally:
        del frame


__all__ = [
    "abrir_chrome",
    "abrir_chrome_pantalla",
    "cerrar_chrome",
    "calibrar_chrome",
    "mover_chrome_pantalla",
    "maximizar_chrome",
    "get_chrome_commands",
    "get_chrome_action_commands",
]
