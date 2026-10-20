"""
Funciones específicas para Mozilla Firefox.

La geometría de monitores se obtiene exclusivamente de ScreenManager.
Este módulo conserva funciones antiguas por compatibilidad, pero no genera
coordenadas artificiales, no asume dos monitores y no utiliza una resolución
ni un DPI fijo.

La calibración real de aplicaciones debe pasar por el flujo universal:
    CalibrationManager -> ScreenManager -> UniversalVisualCalibrator -> Qwen3-VL.
"""

from src.utils.logger import get_logger
import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyautogui
import pygetwindow as gw

from src.utils.screen_manager import get_screen_manager


logger = get_logger(__name__)


# ============================================================================
# UTILIDADES DE FIREFOX
# ============================================================================


def _get_firefox_windows() -> List[Any]:
    """Obtiene las ventanas localizables de Mozilla Firefox."""
    windows: List[Any] = []
    seen = set()

    for title in ("Mozilla Firefox", "Mozilla", "Firefox"):
        try:
            candidates = gw.getWindowsWithTitle(title)
        except Exception as exc:
            logger._print_log("DEBUG", f"[FIREFOX] Error buscando ventanas con título {title}: {exc}", "firefox.py", "_get_firefox_windows", 45)
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


def _get_firefox_window_info(window: Any) -> Optional[Dict[str, Any]]:
    """Obtiene metadatos y geometría actual de una ventana de Firefox."""
    if window is None:
        return None

    try:
        is_visible = True
        if hasattr(window, "is_visible"):
            try:
                is_visible = bool(window.is_visible())
            except Exception:
                is_visible = True

        return {
            "title": str(getattr(window, "title", "") or ""),
            "handle": getattr(window, "_hWnd", None),
            "left": int(getattr(window, "left")),
            "top": int(getattr(window, "top")),
            "width": max(1, int(getattr(window, "width"))),
            "height": max(1, int(getattr(window, "height"))),
            "is_maximized": bool(getattr(window, "isMaximized", False)),
            "is_minimized": bool(getattr(window, "isMinimized", False)),
            "visible": is_visible,
        }
    except Exception as exc:
        logger.DEBUG(r"[FIREFOX] No se pudo obtener información de la ventana: %s  [file:firefox.py, method:_get_firefox_window_info, line:89]"))
        return None


def _find_firefox_window_on_monitor(pantalla: int) -> Optional[Any]:
    """Busca una ventana de Firefox cuyo centro esté dentro del monitor indicado."""
    screen_manager = get_screen_manager()
    screen_manager.refresh_monitors()
    monitor = screen_manager.get_monitor(pantalla)
    if monitor is None:
        return None

    for win in _get_firefox_windows():
        info = _get_firefox_window_info(win)
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


def _select_firefox_window(
    preferred_monitor: Optional[int] = None,
) -> Optional[Any]:
    """Selecciona una ventana Firefox, priorizando el monitor indicado."""
    if preferred_monitor is not None:
        window = _find_firefox_window_on_monitor(preferred_monitor)
        if window is not None:
            return window

    windows = _get_firefox_windows()
    for window in windows:
        info = _get_firefox_window_info(window)
        if info and info.get("visible", True):
            return window

    return windows[0] if windows else None


# ============================================================================
# SITIOS WEB
# ============================================================================


def abrir_youtube() -> str:
    """Abre YouTube en el navegador predeterminado."""
    try:
        webbrowser.open("https://www.youtube.com")
        return "He abierto YouTube en tu navegador."
    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error abriendo YouTube: %s  [file:firefox.py, method:abrir_youtube, line:147]"))
        return f"Error al abrir YouTube: {exc}"


def abrir_spotify() -> str:
    """Abre Spotify Web en el navegador predeterminado."""
    try:
        webbrowser.open("https://open.spotify.com")
        return "He abierto Spotify en tu navegador."
    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error abriendo Spotify: %s  [file:firefox.py, method:abrir_spotify, line:157]"))
        return f"Error al abrir Spotify: {exc}"


# ============================================================================
# APERTURA DE FIREFOX
# ============================================================================


def abrir_firefox_pantalla(pantalla: int = 1) -> str:
    """Abre Mozilla Firefox y lo posiciona en la pantalla solicitada."""
    logger.INFO(r"[FIREFOX] Abriendo Firefox en pantalla %s...  [file:firefox.py, method:abrir_firefox_pantalla, line:168]"))

    try:
        if pantalla < 1:
            return "Error: el número de pantalla debe ser mayor que 0."

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla)
        if monitor is None:
            return (
                f"Error: la pantalla {pantalla} no existe. "
                f"Hay {len(screen_manager.monitors)} pantalla(s) detectada(s)."
            )

        firefox_window = _select_firefox_window()

        if not _verificar_firefox_abierto():
            if not _abrir_firefox_desde_ruta():
                return "Error: no se pudo iniciar Mozilla Firefox."
            time.sleep(1.5)
        elif firefox_window is not None:
            try:
                firefox_window.activate()
            except Exception:
                pass

        firefox_window = _select_firefox_window(preferred_monitor=pantalla)
        if firefox_window is None:
            time.sleep(1.0)
            firefox_window = _select_firefox_window(preferred_monitor=pantalla)

        if firefox_window is None:
            logger.warning(
                "[FIREFOX] Firefox está abierto pero no se encontró su ventana."
            )
            return (
                "Mozilla Firefox está abierto, pero no he podido localizar su "
                f"ventana para la pantalla {pantalla}."
            )

        if not _move_firefox_window(firefox_window, monitor):
            return (
                "Mozilla Firefox está abierto, pero no he podido posicionarlo "
                f"en la pantalla {pantalla}."
            )

        return f"He abierto Mozilla Firefox en tu pantalla {pantalla}."

    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error al abrir Firefox en pantalla %s: %s  [file:firefox.py, method:abrir_firefox_pantalla, line:218]"))
        return f"Error al abrir Firefox en pantalla {pantalla}: {exc}"


def abrir_firefox_pestana(pantalla: int = 1) -> str:
    """Abre una nueva pestaña de Firefox en la pantalla solicitada."""
    logger.INFO(r"[FIREFOX] Abriendo nueva pestaña de Firefox en pantalla %s...  [file:firefox.py, method:abrir_firefox_pestana, line:224]"))

    try:
        if pantalla < 1:
            return "Error: el número de pantalla debe ser mayor que 0."

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla)
        if monitor is None:
            return (
                f"Error: la pantalla {pantalla} no existe. "
                f"Hay {len(screen_manager.monitors)} pantalla(s) detectada(s)."
            )

        win = _select_firefox_window(preferred_monitor=pantalla)

        if win is None:
            if not _abrir_firefox_desde_ruta():
                return "Error: no se pudo iniciar Mozilla Firefox."
            time.sleep(1.5)
            win = _select_firefox_window(preferred_monitor=pantalla)

        if win is None:
            return "Error: no se pudo localizar la ventana de Mozilla Firefox."

        info = _get_firefox_window_info(win)
        if info:
            center_x = info["left"] + info["width"] // 2
            center_y = info["top"] + info["height"] // 2
            try:
                already_on_monitor = monitor.contains_point(center_x, center_y)
            except Exception:
                already_on_monitor = False

            if not already_on_monitor:
                if not _move_firefox_window(win, monitor):
                    return (
                        "Error: no se pudo mover Firefox a la "
                        f"pantalla {pantalla}."
                    )

        try:
            win.activate()
        except Exception:
            pass

        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "t")
        time.sleep(0.3)

        logger.INFO(r"[FIREFOX] Nueva pestaña abierta en pantalla %s  [file:firefox.py, method:abrir_firefox_pestana, line:275]"))
        return (
            "He abierto una nueva pestaña en tu Mozilla Firefox "
            f"de la pantalla {pantalla}."
        )

    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error al intentar manipular Firefox: %s  [file:firefox.py, method:abrir_firefox_pestana, line:282]"))
        return f"Error al abrir una nueva pestaña de Firefox: {exc}"


# ============================================================================
# APERTURA DESDE RUTA
# ============================================================================


def _candidate_firefox_paths() -> List[str]:
    """Devuelve rutas habituales donde puede estar instalado Firefox."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get(
        "PROGRAMFILES(X86)",
        r"C:\Program Files (x86)",
    )

    candidates = [
        shutil.which("firefox"),
        os.path.join(program_files, "Mozilla Firefox", "firefox.exe"),
        os.path.join(program_files_x86, "Mozilla Firefox", "firefox.exe"),
        os.path.join(local_app_data, "Mozilla Firefox", "firefox.exe"),
    ]

    result: List[str] = []
    seen = set()
    for path in candidates:
        if not path:
            continue
        expanded = os.path.abspath(os.path.expandvars(path))
        normalized = os.path.normcase(expanded)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(expanded)

    return result


def _abrir_firefox_desde_ruta() -> bool:
    """Abre Firefox desde una instalación local conocida."""
    try:
        for ruta in _candidate_firefox_paths():
            try:
                if not os.path.isfile(ruta):
                    logger.DEBUG(r"[FIREFOX] Ruta no encontrada: %s  [file:firefox.py, method:_candidate_firefox_paths, line:328]"))
                    continue

                logger.INFO(r"[FIREFOX] Abriendo Firefox desde: %s  [file:firefox.py, method:_abrir_firefox_desde_ruta, line:331]"))
                subprocess.Popen([ruta], close_fds=True)
                time.sleep(1.5)
                return True
            except (OSError, subprocess.SubprocessError) as exc:
                logger.DEBUG(r"[FIREFOX] Error con ruta %s: %s  [file:firefox.py, method:_abrir_firefox_desde_ruta, line:337]"))

        logger.WARNING(r"[FIREFOX] No se encontró firefox.exe en las rutas habituales; intentando webbrowser...  [file:firefox.py, method:_abrir_firefox_desde_ruta, line:343]"))
        try:
            webbrowser.open("https://www.google.com")
            time.sleep(2.0)
            return True
        except Exception as exc:
            logger.ERROR(r"[FIREFOX] Fallback webbrowser falló: %s  [file:firefox.py, method:_abrir_firefox_desde_ruta, line:351]"))
            return False

    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error abriendo Firefox: %s  [file:firefox.py, method:_abrir_firefox_desde_ruta, line:355]"))
        return False


# ============================================================================
# DETECCIÓN
# ============================================================================


def _verificar_firefox_abierto() -> bool:
    """Verifica si Firefox está abierto y visible."""
    try:
        for win in _get_firefox_windows():
            try:
                if hasattr(win, "is_visible") and not bool(win.is_visible()):
                    continue
                return True
            except Exception:
                continue

        return False

    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error verificando Firefox: %s  [file:firefox.py, method:_verificar_firefox_abierto, line:372]"))
        return False


def _verificar_firefox_instalado() -> bool:
    """Verifica si Mozilla Firefox está instalado."""
    try:
        for ruta in _candidate_firefox_paths():
            if os.path.isfile(ruta):
                return True

        try:
            result = subprocess.run(
                ["firefox", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        try:
            import winreg

            rutas_registro = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
            ]

            for key_path in rutas_registro:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        key_path,
                    ) as key:
                        winreg.QueryValueEx(key, None)
                    return True
                except OSError:
                    continue
        except ImportError:
            pass

        return False

    except Exception as exc:
        logger.debug(
            "[FIREFOX] Error verificando Firefox instalado: %s",
            exc,
        )
        return False


# ============================================================================
# MOVIMIENTO
# ============================================================================


def _move_firefox_window(window: Any, monitor: Any) -> bool:
    """Mueve una ventana Firefox al origen del monitor y trata de maximizarla."""
    if window is None or monitor is None:
        return False

    try:
        window.moveTo(int(monitor.left), int(monitor.top))
        try:
            window.maximize()
        except Exception as exc:
            logger.debug(
                "[FIREFOX] No se pudo maximizar Firefox: %s",
                exc,
            )
        return True
    except Exception as exc:
        logger.warning(
            "[FIREFOX] No se pudo mover Firefox al monitor: %s",
            exc,
        )
        return False


def _mover_firefox_a_pantalla(pantalla_num: int) -> bool:
    """Mueve una ventana de Firefox al monitor solicitado."""
    try:
        if pantalla_num < 1:
            logger.warning(
                "[FIREFOX] Número de pantalla inválido: %s",
                pantalla_num,
            )
            return False

        screen_manager = get_screen_manager()
        screen_manager.refresh_monitors()
        monitor = screen_manager.get_monitor(pantalla_num)
        if monitor is None:
            logger.warning(
                "[FIREFOX] El monitor %s no existe",
                pantalla_num,
            )
            return False

        win = _select_firefox_window(preferred_monitor=pantalla_num)
        if win is None:
            logger.warning(
                "[FIREFOX] No se encontró ventana de Firefox para mover"
            )
            return False

        if _move_firefox_window(win, monitor):
            logger.info(
                "[FIREFOX] Ventana de Firefox movida a pantalla %s "
                "(x=%s, y=%s)",
                pantalla_num,
                monitor.left,
                monitor.top,
            )
            return True

        return False

    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error moviendo Firefox a pantalla %s: %s  [file:firefox.py, method:_mover_firefox_a_pantalla, line:496]"))
        return False


# ============================================================================
# CIERRE
# ============================================================================


def _cerrar_firefox() -> bool:
    """Cierra una ventana visible de Firefox."""
    try:
        win = _select_firefox_window()
        if win is None:
            return False

        win.close()
        logger.INFO(r"[FIREFOX] Firefox cerrado  [file:firefox.py, method:_cerrar_firefox, line:520]"))
        time.sleep(1.0)
        return True

    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error cerrando Firefox: %s  [file:firefox.py, method:_cerrar_firefox, line:526]"))
        return False


# ============================================================================
# CALIBRACIÓN LEGACY
# ============================================================================


def _calibrar_firefox() -> Dict[str, Any]:
    """
    Compatibilidad con la implementación antigua.

    La calibración real de aplicaciones pasa por el flujo universal:
        CalibrationManager
            -> ScreenManager
            -> captura del monitor
            -> UniversalVisualCalibrator
            -> Qwen3-VL

    Esta función no fabrica coordenadas.
    """
    logger.WARNING(r"[FIREFOX] _calibrar_firefox() es una función legacy. La calibración real utiliza el flujo universal.  [file:firefox.py, method:_calibrar_firefox, line:552]"))
    return {
        "aplicacion": "firefox",
        "elementos_calibrados": [],
        "intentos_realizados": 0,
        "exitosos": 0,
        "timestamp": time.time(),
        "deprecated": True,
        "error": (
            "La calibración específica legacy de Firefox ha sido desactivada. "
            "Utiliza el calibrador universal de aplicaciones."
        ),
    }


def _generar_coordenadas_firefox(tipo_elemento: str) -> Dict[str, int]:
    """Compatibilidad con código legacy; no genera coordenadas artificiales."""
    logger.warning(
        "[FIREFOX] Se solicitó una coordenada legacy para '%s', "
        "pero no se generan coordenadas artificiales.",
        tipo_elemento,
    )
    return {}


# ============================================================================
# CAPTURA LEGACY
# ============================================================================


def _capturar_firefox() -> Optional[str]:
    """
    Captura la ventana visible de Firefox.

    Se conserva para compatibilidad. La calibración universal trabaja
    preferentemente con la captura completa del monitor mediante ScreenManager.
    """
    try:
        win = _select_firefox_window()
        if win is None:
            logger.warning(
                "[FIREFOX] No se encontró ventana de Firefox para capturar"
            )
            return None

        info = _get_firefox_window_info(win)
        if info is None:
            return None

        width = info["width"]
        height = info["height"]
        if width <= 0 or height <= 0:
            logger.WARNING(r"[FIREFOX] Dimensiones de ventana inválidas  [file:firefox.py, method:get_window_dimensions, line:590]"))
            return None

        screenshot = pyautogui.screenshot(
            region=(
                info["left"],
                info["top"],
                width,
                height,
            )
        )

        project_root = get_screen_manager().project_root
        temp_path = (
            Path(project_root)
            / f"temp_firefox_{int(time.time() * 1000)}.png"
        )
        screenshot.save(temp_path)
        logger.INFO(r"[FIREFOX] Captura de Firefox guardada: %s  [file:firefox.py, method:_capturar_firefox, line:618]"))
        return str(temp_path)

    except Exception as exc:
        logger.ERROR(r"[FIREFOX] Error capturando Firefox: %s  [file:firefox.py, method:_capturar_firefox, line:625]"))
        return None


# ============================================================================
# COMANDOS
# ============================================================================


def get_firefox_commands() -> list:
    """Obtiene los comandos legacy de Firefox."""
    return [
        "abrir_youtube",
        "abrir_spotify",
        "abrir_firefox_pantalla",
        "abrir_firefox_pestana",
        "_abrir_firefox_desde_ruta",
        "_verificar_firefox_abierto",
        "_verificar_firefox_instalado",
        "_mover_firefox_a_pantalla",
        "_cerrar_firefox",
        "_calibrar_firefox",
        "_generar_coordenadas_firefox",
        "_capturar_firefox",
    ]
