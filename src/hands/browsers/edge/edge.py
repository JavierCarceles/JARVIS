"""
Funciones especificas para Microsoft Edge.

La geometria de monitores se obtiene exclusivamente de ScreenManager.
Este modulo conserva funciones antiguas por compatibilidad, pero no genera
coordenadas artificiales, no asume dos monitores y no utiliza una resolucion
ni un DPI fijo.
"""

from src.core.log import get_logger
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys as _sys

from src.desktop.native_imports import lazy_module as _lazy_module, lazy_windll as _lazy_windll

if _sys.platform == "win32":
    import pyautogui
    import pygetwindow as gw
else:
    pyautogui = _lazy_module("pyautogui")  # import perezoso fuera de Windows
    gw = _lazy_module("pygetwindow")  # import nativo perezoso fuera de Windows

from src.desktop.screen_manager import get_screen_manager


logger = get_logger(__name__)


# ============================================================================
# UTILIDADES DE EDGE
# ============================================================================


def _get_edge_windows() -> List[Any]:
    """Obtiene las ventanas visibles/localizables de Microsoft Edge."""
    windows: List[Any] = []
    seen: set = set()

    for title in ("Microsoft Edge", "Microsoft", "Edge"):
        try:
            candidates = gw.getWindowsWithTitle(title)
        except Exception as exc:
            logger.debug(f"[EDGE] Error buscando ventanas con titulo {title!r}: {exc}")

            continue

        for win in candidates:
            try:
                identity = getattr(win, "_hWnd", None)
                if identity is None:
                    identity = id(win)
                if identity in seen:
                    continue
                seen.add(identity)
                windows.append(win)
            except Exception:
                if win not in windows:
                    windows.append(win)

    return windows


def _get_edge_window_info(window: Any) -> Optional[Dict[str, Any]]:
    """Obtiene metadatos y geometria actual de una ventana de Edge."""
    if window is None:
        return None

    try:
        return {
            "title": str(getattr(window, "title", "") or ""),
            "handle": getattr(window, "_hWnd", None),
            "left": int(getattr(window, "left")),
            "top": int(getattr(window, "top")),
            "width": max(1, int(getattr(window, "width"))),
            "height": max(1, int(getattr(window, "height"))),
            "is_maximized": bool(getattr(window, "isMaximized", False)),
            "is_minimized": bool(getattr(window, "isMinimized", False)),
            "visible": bool(window.is_visible())
            if hasattr(window, "is_visible")
            else True,
        }
    except Exception as exc:
        logger.debug(r"[EDGE] No se pudo obtener informacion de la ventana: %s", exc)

        return None


def _find_edge_window_on_monitor(pantalla: int) -> Optional[Any]:
    """Busca una ventana de Edge cuyo centro este dentro del monitor indicado."""
    screen_manager = get_screen_manager()
    screen_manager.refresh_monitors()
    monitor = screen_manager.get_monitor(pantalla)
    if monitor is None:
        return None

    for win in _get_edge_windows():
        info = _get_edge_window_info(win)
        if not info or not info.get("visible", True):
            continue

        center_x = info["left"] + info["width"] // 2
        center_y = info["top"] + info["height"] // 2
        try:
            if monitor.contains_point(center_x, center_y):
                return win
        except Exception:
            continue

    return None


def _select_edge_window(preferred_monitor: Optional[int] = None) -> Optional[Any]:
    """Selecciona una ventana Edge, priorizando el monitor indicado."""
    if preferred_monitor is not None:
        window = _find_edge_window_on_monitor(preferred_monitor)
        if window is not None:
            return window

    windows = _get_edge_windows()
    for window in windows:
        info = _get_edge_window_info(window)
        if info and info.get("visible", True):
            return window

    return windows[0] if windows else None


# ============================================================================
# APERTURA DE EDGE
# ============================================================================


def abrir_edge_pantalla(pantalla: int = 1) -> str:
    """Abre Microsoft Edge y lo posiciona en la pantalla solicitada."""


    try:
        if pantalla < 1:
            return "Error: el n\u00famero de pantalla debe ser mayor que 0."

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla)
        if monitor is None:
            return (
                f"Error: la pantalla {pantalla} no existe. "
                f"Hay {len(screen_manager.monitors)} pantalla(s) detectada(s)."
            )

        window_before = _select_edge_window()

        if not _verificar_edge_abierto():
            if not _abrir_edge_desde_ruta():
                return "Error: no se pudo iniciar Microsoft Edge."
            time.sleep(1.5)
        else:
            try:
                if window_before is not None:
                    window_before.activate()
            except Exception:
                pass

        edge_window = _select_edge_window(preferred_monitor=pantalla)
        if edge_window is None:
            time.sleep(1.0)
            edge_window = _select_edge_window(preferred_monitor=pantalla)

        if edge_window is None:
            logger.warning(r"[EDGE] Edge se abrio pero no se encontro su ventana.")

            return (
                f"Microsoft Edge est\u00e1 abierto, pero no he podido localizar su "
                f"ventana para la pantalla {pantalla}."
            )

        if not _move_edge_window(edge_window, monitor):
            return (
                f"Microsoft Edge est\u00e1 abierto, pero no he podido posicionarlo "
                f"en la pantalla {pantalla}."
            )

        return f"He abierto Microsoft Edge en tu pantalla {pantalla}."

    except Exception as exc:
        logger.error(r"[EDGE] Error al abrir Edge en pantalla %s: %s", pantalla, exc)

        return f"Error al abrir Edge en pantalla {pantalla}: {exc}"


def abrir_edge_pestana(pantalla: int = 1) -> str:
    """Abre una nueva pestana de Edge en la pantalla solicitada."""


    try:
        if pantalla < 1:
            return "Error: el n\u00famero de pantalla debe ser mayor que 0."

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla)
        if monitor is None:
            return (
                f"Error: la pantalla {pantalla} no existe. "
                f"Hay {len(screen_manager.monitors)} pantalla(s) detectada(s)."
            )

        win = _select_edge_window(preferred_monitor=pantalla)

        if win is None:
            if not _abrir_edge_desde_ruta():
                return "Error: no se pudo iniciar Microsoft Edge."
            time.sleep(1.5)
            win = _select_edge_window(preferred_monitor=pantalla)

        if win is None:
            return "Error: no se pudo localizar la ventana de Microsoft Edge."

        # Si Edge esta en otro monitor, se mueve a la geometria real solicitada.
        info = _get_edge_window_info(win)
        if info:
            center_x = info["left"] + info["width"] // 2
            center_y = info["top"] + info["height"] // 2
            try:
                already_on_monitor = monitor.contains_point(center_x, center_y)
            except Exception:
                already_on_monitor = False
            if not already_on_monitor:
                _move_edge_window(win, monitor)

        try:
            win.activate()
        except Exception:
            pass

        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "t")
        time.sleep(0.3)


        return (
            "He abierto una nueva pesta\u00f1a en tu Microsoft Edge "
            f"de la pantalla {pantalla}."
        )

    except Exception as exc:
        logger.error(r"[EDGE] Error al intentar manipular Edge: %s", exc)

        return f"Error al abrir una nueva pesta\u00f1a de Edge: {exc}"


# ============================================================================
# APERTURA DESDE RUTA
# ============================================================================


def _candidate_edge_paths() -> List[str]:
    """Devuelve rutas habituales donde puede estar instalado Edge."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")

    candidates = [
        shutil.which("msedge"),
        os.path.join(
            program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"
        ),
        os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(local_app_data, "Microsoft", "Edge", "Application", "msedge.exe"),
    ]

    result: List[str] = []
    seen = set()
    for path in candidates:
        if not path:
            continue
        normalized = os.path.normcase(os.path.abspath(os.path.expandvars(path)))
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(os.path.abspath(os.path.expandvars(path)))
    return result


def _abrir_edge_desde_ruta() -> bool:
    """Abre Edge desde una instalacion local conocida."""
    try:
        for ruta in _candidate_edge_paths():
            try:
                if not os.path.isfile(ruta):
                    logger.debug(r"[EDGE] Ruta no encontrada: %s", ruta)

                    continue


                subprocess.Popen([ruta], close_fds=True)
                time.sleep(1.5)
                return True
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug(r"[EDGE] Error con ruta %s: %s", ruta, exc)


        logger.warning("[EDGE] No se encontro msedge.exe en las rutas habituales.")

        return False

    except Exception as exc:
        logger.error(r"[EDGE] Error abriendo Edge: %s", exc)
        return False


# ============================================================================
# DETECCION
# ============================================================================


def _verificar_edge_abierto() -> bool:
    """Verifica si Edge esta abierto y visible."""
    try:
        for win in _get_edge_windows():
            try:
                if hasattr(win, "is_visible") and not bool(win.is_visible()):
                    continue
                return True
            except Exception:
                continue

        return False

    except Exception as exc:
        logger.error(r"[EDGE] Error verificando Edge: %s", exc)
        return False


def _verificar_edge_instalado() -> bool:
    """Verifica si Microsoft Edge esta instalado."""
    try:
        for ruta in _candidate_edge_paths():
            if os.path.isfile(ruta):
                return True

        try:
            result = subprocess.run(
                ["msedge", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        try:
            import winreg

            rutas_registro = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            ]

            for key_path in rutas_registro:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                        winreg.QueryValueEx(key, None)
                    return True
                except OSError:
                    continue
        except ImportError:
            pass

        return False

    except Exception as exc:
        logger.debug(r"[EDGE] Error verificando Edge instalado: %s", exc)
        return False


# ============================================================================
# MOVIMIENTO
# ============================================================================


def _move_edge_window(window: Any, monitor: Any) -> bool:
    """Mueve una ventana Edge al origen del monitor y trata de maximizarla."""
    if window is None or monitor is None:
        return False

    try:
        window.moveTo(int(monitor.left), int(monitor.top))
        try:
            window.maximize()
        except Exception as exc:
            logger.debug(r"[EDGE] No se pudo maximizar Edge: %s", exc)
        return True
    except Exception as exc:
        logger.warning(r"[EDGE] No se pudo mover Edge al monitor: %s", exc)
        return False


def _mover_edge_a_pantalla(pantalla_num: int) -> bool:
    """Mueve una ventana de Edge al monitor solicitado."""
    try:
        if pantalla_num < 1:
            logger.warning(r"[EDGE] Numero de pantalla invalido: %s", pantalla_num)
            return False

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla_num)
        if monitor is None:
            logger.warning(r"[EDGE] El monitor %s no existe", pantalla_num)
            return False

        win = _select_edge_window(preferred_monitor=pantalla_num)
        if win is None:
            logger.warning("[EDGE] No se encontro ventana de Edge para mover")

            return False

        if _move_edge_window(win, monitor):
            logger.info(
                "[EDGE] Ventana de Edge movida a pantalla %s (x=%s, y=%s)",
                pantalla_num,
                monitor.left,
                monitor.top,
            )
            return True

        return False

    except Exception as exc:
        logger.debug("_mover_edge_a_pantalla: %s", exc)

        return False


# ============================================================================
# CIERRE
# ============================================================================


def _cerrar_edge() -> bool:
    """Cierra una ventana visible de Edge."""
    try:
        win = _select_edge_window()
        if win is None:
            return False

        win.close()
        logger.info(r"[EDGE] Edge cerrado")
        time.sleep(1.0)
        return True

    except Exception as exc:
        logger.error(r"[EDGE] Error cerrando Edge: %s", exc)
        return False


# ============================================================================
# CALIBRACION LEGACY
# ============================================================================


def _calibrar_edge() -> Dict[str, Any]:
    """
    Compatibilidad con la implementacion antigua.

    La calibracion real de aplicaciones pasa por el flujo universal:
        CalibrationManager
            -> ScreenManager
            -> captura del monitor
            -> UniversalVisualCalibrator
            -> Qwen3-VL

    Esta funcion no fabrica coordenadas.
    """
    logger.warning(
        "[EDGE] _calibrar_edge() es una funcion legacy. "
        "La calibracion real utiliza el flujo universal."
    )
    return {
        "aplicacion": "edge",
        "elementos_calibrados": [],
        "intentos_realizados": 0,
        "exitosos": 0,
        "timestamp": time.time(),
        "deprecated": True,
        "error": (
            "La calibraci\u00f3n espec\u00edfica legacy de Edge ha sido desactivada. "
            "Utiliza el calibrador universal de aplicaciones."
        ),
    }


def _generar_coordenadas_edge(tipo_elemento: str) -> Dict[str, int]:
    """Compatibilidad con codigo antiguo; no genera coordenadas artificiales."""
    logger.warning(
        "[EDGE] Se solicito una coordenada legacy para '%s', "
        "pero no se generan coordenadas artificiales.",
        tipo_elemento,
    )
    return {}


# ============================================================================
# CAPTURA
# ============================================================================


def _capturar_edge() -> Optional[str]:
    """
    Captura la ventana visible de Edge.

    Se conserva para compatibilidad. La calibracion universal trabaja
    preferentemente con la captura completa del monitor mediante ScreenManager.
    """
    try:
        win = _select_edge_window()
        if win is None:
            logger.warning(r"[EDGE] No se encontro ventana de Edge para capturar")
            return None

        info = _get_edge_window_info(win)
        if not info:
            return None

        screenshot = pyautogui.screenshot(
            region=(
                info["left"],
                info["top"],
                info["width"],
                info["height"],
            )
        )

        project_root = get_screen_manager().project_root
        temp_path = Path(project_root) / f"temp_edge_{int(time.time() * 1000)}.png"
        screenshot.save(temp_path)
        logger.info(r"[EDGE] Captura de Edge guardada: %s", temp_path)
        return str(temp_path)

    except Exception as exc:
        logger.error(r"[EDGE] Error capturando Edge: %s", exc)
        return None


# ============================================================================
# COMANDOS
# ============================================================================


def get_edge_commands() -> list:
    """Obtiene los comandos legacy de Edge."""
    return [
        "abrir_edge_pantalla",
        "abrir_edge_pestana",
        "_abrir_edge_desde_ruta",
        "_verificar_edge_abierto",
        "_verificar_edge_instalado",
        "_mover_edge_a_pantalla",
        "_cerrar_edge",
        "_calibrar_edge",
        "_generar_coordenadas_edge",
        "_capturar_edge",
    ]

