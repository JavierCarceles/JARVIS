"""
Funciones auxiliares para aplicaciones de Windows.

La geometría de monitores y las coordenadas se obtienen exclusivamente
mediante ScreenManager.

La calibración universal de aplicaciones NO utiliza coordenadas manuales
ni tablas específicas por aplicación.

Flujo oficial de calibración:

    CalibrationManager
        -> aplicación
        -> ventana
        -> ScreenManager
        -> monitor real
        -> captura
        -> UniversalVisualCalibrator
        -> Qwen3-VL
        -> coordenadas absolutas

Este módulo mantiene utilidades y APIs legacy para compatibilidad. La
calibración universal no debe depender de funciones específicas de Notepad,
Calculator, Paint, Explorer o CMD.
"""

from __future__ import annotations

import os
import platform
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyautogui
import pygetwindow as gw

from src.utils.logger import get_logger
from src.utils.screen_manager import get_screen_manager

logger = get_logger(__name__)


# ============================================================================
# RIOT API KEY
# ============================================================================


def actualizar_api_key_riot() -> str:
    """
    Abre Riot Developer Portal y solicita un análisis visual.

    Esta acción es independiente de la calibración universal de aplicaciones.
    """
    logger._print_log("info", "[WINDOWS] Iniciando actualización de API Key de Riot Games...", "windows.py", "method", 57)
    screenshot_path: Optional[str] = None
    try:
        webbrowser.open("https://developer.riotgames.com/")
        time.sleep(3)
        screenshot_path = _capturar_pantalla()
        if not screenshot_path:
            return (
                "Página de Riot Developer Portal abierta. "
                "No se pudo capturar la pantalla."
            )

        analysis_prompt = (
            "Analiza exclusivamente la interfaz visible del Riot Developer "
            "Portal. Busca elementos interactivos relacionados con la API "
            "Key, como campos de texto, botones de regeneración o actualización "
            "y controles asociados. Devuelve información visual útil para "
            "automatización."
        )
        try:
            from src.eyes import Vision

            vision = Vision()
            analysis_result = vision.analyze_image(
                screenshot_path,
                analysis_prompt,
            )
            logger._print_log("info", "[WINDOWS] Análisis de Riot completado.", "windows.py", "method", 84)
            return (
                "He encontrado la página de Riot Developer Portal. "
                f"Análisis: {analysis_result}"
            )
        except Exception as exc:
            logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
            return (
                "Página de Riot Developer Portal abierta. "
                "El análisis visual ha fallado."
            )
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
        return "Error al actualizar API Key de Riot."
    finally:
        if screenshot_path:
            try:
                path = Path(screenshot_path)
                if path.exists():
                    path.unlink()
            except Exception as exc:
                logger.debug(
                    "[WINDOWS] No se pudo eliminar captura temporal: %s",
                    exc,
                )


# ============================================================================
# CAPTURA DE PANTALLA
# ============================================================================


def _capturar_pantalla(filepath: str = "screenshot.png") -> Optional[str]:
    """
    Captura el escritorio completo.

    Se delega primero en ScreenManager para mantener una única implementación
    de captura dentro de Jarvis.
    """
    logger._print_log("debug", "[WINDOWS] Capturando escritorio completo...", "windows.py", "method", 123)
    try:
        screen_manager = get_screen_manager()
        capture_method = getattr(screen_manager, "capture_screen", None)
        if callable(capture_method):
            result = capture_method()
            if result:
                return str(result)
    except Exception as exc:
        logger.debug(
            "[WINDOWS] ScreenManager no pudo capturar escritorio: %s",
            exc,
        )

    try:
        screenshot = pyautogui.screenshot()
        path = Path(filepath)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        screenshot.save(path)
        logger._print_log("debug", [WINDOWS] Captura guardada: %s, "windows.py", "method", 144)
        return str(path)
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
        return None


# ============================================================================
# APERTURA DE APLICACIONES
# ============================================================================


def _abrir_aplicacion_windows(nombre_app: str) -> bool:
    """
    Intenta abrir una aplicación de Windows.

    Esta función es legacy. La gestión universal de aplicaciones para
    calibración la realiza CalibrationManager. No contiene una tabla de
    coordenadas ni depende de aplicaciones concretas para decidir la
    geometría de pantalla.
    """
    if not str(nombre_app or "").strip():
        return False

    nombre = str(nombre_app).strip()
    logger._print_log("info", [WINDOWS] Abriendo aplicación: %s, "windows.py", "method", 169)

    # 1) Intentar el gestor centralizado para aplicaciones conocidas.
    try:
        from src.hands.calibration_manager import get_calibration_manager

        manager = get_calibration_manager()
        launcher = getattr(manager, "launch_application", None)
        resolver = getattr(manager, "_resolve_application", None)
        if callable(launcher) and callable(resolver):
            application = resolver(nombre)
            if application is not None:
                window = launcher(application)
                if window is not None:
                    logger.info(
                        "[WINDOWS] Aplicación abierta mediante CalibrationManager: %s",
                        nombre,
                    )
                    return True
    except Exception as exc:
        logger.debug(
            "[WINDOWS] CalibrationManager no pudo abrir %s: %s",
            nombre,
            exc,
        )

    # 2) Fallback genérico: pedir a Windows que resuelva el nombre/URI.
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", nombre],
            shell=False,
        )
        time.sleep(2)
        if _verificar_aplicacion_abierta(nombre):
            return True

        # Algunos accesos o aplicaciones de Windows pueden tardar más en
        # crear una ventana visible. No relanzamos innecesariamente.
        time.sleep(1)
        return _verificar_aplicacion_abierta(nombre)
    except Exception as exc:
        logger.debug(
            "[WINDOWS] No se pudo iniciar '%s' mediante start: %s",
            nombre,
            exc,
        )
        return False


# ============================================================================
# DETECCIÓN DE VENTANAS
# ============================================================================


def _get_window_search_patterns(nombre_app: str) -> List[str]:
    """
    Devuelve patrones de título compatibles con aplicaciones comunes.

    Esta función se conserva únicamente como fallback legacy. No debe usarse
    para determinar el monitor de una ventana durante la calibración universal.
    """
    name = str(nombre_app or "").strip()
    if not name:
        return []

    patterns: List[str] = [name]
    lower = name.lower()
    aliases = {
        "notepad": ["Notepad", "Bloc de notas"],
        "bloc de notas": ["Notepad", "Bloc de notas"],
        "calculator": ["Calculator", "Calculadora"],
        "calculadora": ["Calculator", "Calculadora"],
        "paint": ["Paint", "mspaint"],
        "explorer": ["File Explorer", "Explorador de archivos", "Explorer"],
        "explorador de archivos": [
            "File Explorer",
            "Explorador de archivos",
            "Explorer",
        ],
        "cmd": ["cmd", "Command Prompt", "Símbolo del sistema"],
        "command prompt": ["cmd", "Command Prompt", "Símbolo del sistema"],
    }

    for key, values in aliases.items():
        if lower == key or key in lower:
            patterns.extend(values)

    result: List[str] = []
    for pattern in patterns:
        if pattern and pattern not in result:
            result.append(pattern)
    return result


def _get_application_windows(nombre_app: str) -> List[Any]:
    """
    Busca ventanas de una aplicación por título.

    Esta búsqueda es solo una utilidad legacy. No debe utilizarse para inferir
    geometría de monitores ni para construir coordenadas de calibración.
    """
    windows: List[Any] = []
    for pattern in _get_window_search_patterns(nombre_app):
        try:
            matches = gw.getWindowsWithTitle(pattern)
        except Exception as exc:
            logger.debug(
                "[WINDOWS] Error buscando ventana '%s': %s",
                pattern,
                exc,
            )
            continue

        for win in matches:
            if win not in windows:
                windows.append(win)
    return windows


def _verificar_aplicacion_abierta(nombre_app: str) -> bool:
    """Verifica si una aplicación tiene al menos una ventana visible."""
    try:
        time.sleep(0.5)
        windows = _get_application_windows(nombre_app)
        for win in windows:
            try:
                if hasattr(win, "is_visible") and not bool(win.is_visible):
                    continue
                logger.debug(
                    "[WINDOWS] %s detectada y visible",
                    nombre_app,
                )
                return True
            except Exception:
                continue

        logger.debug(
            "[WINDOWS] %s no encontrada entre las ventanas abiertas",
            nombre_app,
        )
        return False
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
        return False


# ============================================================================
# MOVIMIENTO A MONITOR
# ============================================================================


def _mover_aplicacion_a_pantalla(
    nombre_app: str,
    pantalla_num: int,
) -> bool:
    """
    Mueve una aplicación a un monitor concreto.

    Nunca calcula offsets manuales. La posición de destino se obtiene de
    ScreenManager. La lógica universal preferida recibe una ventana/handle,
    pero esta API legacy mantiene el nombre de la aplicación como entrada.
    """
    try:
        screen_number = int(pantalla_num)
    except (TypeError, ValueError):
        logger._print_log("warning", [WINDOWS] Número de monitor inválido: %s, "windows.py", "method", 334)
        return False

    if screen_number < 1:
        logger._print_log("warning", [WINDOWS] Número de monitor inválido: %s, "windows.py", "method", 338)
        return False

    try:
        screen_manager = get_screen_manager()
        refresh = getattr(screen_manager, "refresh_monitors", None)
        if callable(refresh):
            refresh()

        monitor = screen_manager.get_monitor(screen_number)
        if monitor is None:
            logger.warning(
                "[WINDOWS] El monitor %s no existe",
                screen_number,
            )
            return False

        # La implementación centralizada debe ser la primera opción. Ella es
        # responsable de resolver el HWND y de aplicar la geometría real.
        move_method = getattr(screen_manager, "move_window_to_monitor", None)
        if callable(move_method):
            try:
                if bool(move_method(nombre_app, screen_number)):
                    logger.info(
                        "[WINDOWS] %s movida a pantalla %s mediante ScreenManager",
                        nombre_app,
                        screen_number,
                    )
                    return True
            except Exception as exc:
                logger.debug(
                    "[WINDOWS] ScreenManager no pudo mover %s: %s",
                    nombre_app,
                    exc,
                )

        # Fallback legacy por título. No calcula offsets; usa exclusivamente
        # los límites del monitor proporcionados por ScreenManager.
        windows = _get_application_windows(nombre_app)
        if not windows:
            logger.warning(
                "[WINDOWS] No se encontró ventana de %s",
                nombre_app,
            )
            return False

        win = windows[0]
        restore = getattr(win, "restore", None)
        if callable(restore):
            try:
                restore()
                time.sleep(0.2)
            except Exception:
                pass

        move_to = getattr(win, "moveTo", None)
        if not callable(move_to):
            return False

        move_to(int(monitor.left), int(monitor.top))
        logger.info(
            "[WINDOWS] %s movida a pantalla %s (x=%s, y=%s)",
            nombre_app,
            screen_number,
            monitor.left,
            monitor.top,
        )
        return True
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
        return False


# ============================================================================
# CIERRE
# ============================================================================


def _cerrar_aplicacion_windows(nombre_app: str) -> bool:
    """
    Cierra una ventana de la aplicación.

    API legacy. El CalibrationManager debe encargarse de rastrear y cerrar
    exclusivamente las ventanas/procesos que él mismo haya creado durante
    una calibración.
    """
    try:
        # Si el manager conoce los recursos creados por él, deja que gestione
        # primero ese ciclo de vida.
        try:
            from src.hands.calibration_manager import get_calibration_manager

            manager = get_calibration_manager()
            owned_hwnds = getattr(manager, "_last_launch_owned_hwnds", set())
            owned_pids = getattr(manager, "_last_launch_owned_pids", set())
            if owned_hwnds or owned_pids:
                close_owned = getattr(manager, "_close_last_launch_resources", None)
                if callable(close_owned) and bool(close_owned()):
                    logger.info(
                        "[WINDOWS] Recursos de calibración cerrados mediante CalibrationManager: %s",
                        nombre_app,
                    )
                    return True
        except Exception as exc:
            logger.debug(
                "[WINDOWS] No se pudo delegar el cierre de %s al CalibrationManager: %s",
                nombre_app,
                exc,
            )

        # Compatibilidad legacy: cerrar solo la primera ventana encontrada.
        windows = _get_application_windows(nombre_app)
        if not windows:
            return False

        win = windows[0]
        close_method = getattr(win, "close", None)
        if not callable(close_method):
            return False

        close_method()
        logger._print_log("info", [WINDOWS] Ventana de aplicación cerrada: %s, "windows.py", "method", 459)
        time.sleep(1)
        return True
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
        return False


# ============================================================================
# CALIBRACIÓN LEGACY
# ============================================================================


def _get_default_calibration_screen_number(screen_manager: Any) -> Optional[int]:
    """
    Obtiene un monitor real de referencia para una API legacy.

    Se prioriza el monitor primario. No se consulta Chrome ni se inventa un
    número de pantalla.
    """
    monitors = list(getattr(screen_manager, "monitors", []) or [])
    if not monitors:
        return None

    monitor = next(
        (item for item in monitors if bool(getattr(item, "is_primary", False))),
        monitors[0],
    )

    for attr in ("index", "screen_number", "number"):
        value = getattr(monitor, attr, None)
        if isinstance(value, int) and value > 0:
            return value

    screen_key = getattr(monitor, "screen_key", None)
    if callable(screen_key):
        try:
            screen_key = screen_key()
        except Exception:
            screen_key = None
    if isinstance(screen_key, str) and screen_key.lower().startswith("s"):
        suffix = screen_key[1:]
        if suffix.isdigit() and int(suffix) > 0:
            return int(suffix)

    return None


def _calibrar_aplicacion_windows(nombre_app: str) -> Dict[str, Any]:
    """
    API legacy.

    La calibración real de aplicaciones Windows se realiza mediante
    CalibrationManager. Esta función no genera coordenadas.
    """
    logger.warning(
        "[WINDOWS] _calibrar_aplicacion_windows() es legacy. "
        "La calibración real utiliza el flujo universal."
    )
    try:
        from src.hands.calibration_manager import get_calibration_manager

        manager = get_calibration_manager()
        calibrate_method = getattr(manager, "calibrate_application", None)
        if not callable(calibrate_method):
            return {
                "application": nombre_app,
                "success": False,
                "error": ("CalibrationManager no dispone de calibrate_application()."),
            }

        screen_manager = get_screen_manager()
        refresh = getattr(screen_manager, "refresh_monitors", None)
        if callable(refresh):
            refresh()

        screen_number = _get_default_calibration_screen_number(screen_manager)
        if screen_number is None:
            return {
                "application": nombre_app,
                "success": False,
                "error": "No se pudo determinar un monitor real de calibración.",
            }

        result = calibrate_method(nombre_app, screen_number)
        if isinstance(result, dict):
            return result
        if hasattr(result, "__dict__"):
            return dict(result.__dict__)

        return {
            "application": nombre_app,
            "success": bool(result),
            "result": result,
        }
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
        return {
            "application": nombre_app,
            "success": False,
            "error": str(exc),
        }


def _obtener_elementos_aplicacion(nombre_app: str) -> list:
    """
    API legacy.

    Ya no existe una lista fija de elementos por aplicación. Qwen3-VL debe
    detectar los elementos realmente visibles en cada captura.
    """
    logger.debug(
        "[WINDOWS] Solicitud legacy de elementos para '%s'. "
        "La detección ahora es dinámica.",
        nombre_app,
    )
    return []


def _generar_coordenadas_aplicacion(
    nombre_app: str,
    tipo_elemento: str,
) -> Dict[str, int]:
    """
    API legacy.

    Nunca genera coordenadas artificiales.
    """
    logger.warning(
        "[WINDOWS] Se solicitó una coordenada legacy para '%s' de '%s'. "
        "Las coordenadas manuales están desactivadas.",
        tipo_elemento,
        nombre_app,
    )
    return {}


# ============================================================================
# CAPTURA DE APLICACIÓN LEGACY
# ============================================================================


def _capturar_aplicacion_windows(nombre_app: str) -> Optional[str]:
    """
    Captura la ventana de una aplicación.

    Se conserva para compatibilidad. Para calibración universal debe
    utilizarse la captura del monitor gestionada por ScreenManager.
    """
    try:
        windows = _get_application_windows(nombre_app)
        if not windows:
            logger.warning(
                "[WINDOWS] No se encontró ventana de %s para capturar",
                nombre_app,
            )
            return None

        win = windows[0]
        width = max(1, int(getattr(win, "width", 0)))
        height = max(1, int(getattr(win, "height", 0)))
        left = int(getattr(win, "left", 0))
        top = int(getattr(win, "top", 0))

        screenshot = pyautogui.screenshot(
            region=(left, top, width, height),
        )

        screen_manager = get_screen_manager()
        project_root = Path(getattr(screen_manager, "project_root", Path.cwd()))
        temp_dir = project_root / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / (
            f"temp_{_safe_filename(nombre_app)}_{int(time.time() * 1000)}.png"
        )
        screenshot.save(temp_path)
        logger.info(
            "[WINDOWS] Captura de %s guardada: %s",
            nombre_app,
            temp_path,
        )
        return str(temp_path)
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "windows.py", "method", 90)
        return None


# ============================================================================
# UTILIDADES
# ============================================================================


def _safe_filename(value: str) -> str:
    """Convierte un nombre de aplicación en un nombre de archivo seguro."""
    safe = str(value or "application")
    safe = "".join(
        char if char.isalnum() or char in ("-", "_") else "_" for char in safe
    )
    return safe.strip("_") or "application"


# ============================================================================
# COMANDOS
# ============================================================================


def get_windows_commands() -> list:
    """Devuelve las funciones públicas/legacy asociadas a Windows."""
    return [
        "actualizar_api_key_riot",
        "_capturar_pantalla",
        "_abrir_aplicacion_windows",
        "_verificar_aplicacion_abierta",
        "_mover_aplicacion_a_pantalla",
        "_cerrar_aplicacion_windows",
        "_calibrar_aplicacion_windows",
        "_obtener_elementos_aplicacion",
        "_generar_coordenadas_aplicacion",
        "_capturar_aplicacion_windows",
    ]
