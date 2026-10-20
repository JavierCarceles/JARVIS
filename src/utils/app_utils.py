"""

Utilidades comunes para aplicaciones y automatización.



La geometría de monitores procede exclusivamente de ScreenManager.



La detección visual de elementos se realiza mediante Vision/Qwen3-VL.

Este módulo no genera coordenadas ficticias.

"""

import json

import os

import subprocess

import time

import webbrowser

from pathlib import Path

from typing import Any, Dict, List, Optional


import pyautogui

import pygetwindow as gw


from src.eyes.vision import Vision

from src.utils.logger import get_logger

from src.utils.screen_manager import get_screen_manager


logger = get_logger(__name__)


# ============================================================================

# GESTOR DE APLICACIONES

# ============================================================================


class AppManager:
    """

    Gestor general de aplicaciones.



    Las operaciones de monitorización se delegan en ScreenManager.

    """

    def __init__(self) -> None:

        self.screen_manager = get_screen_manager()

        self.screen_manager.refresh_monitors()

        self.setup = self.screen_manager.setup

    # ========================================================================

    # APERTURA

    # ========================================================================

    def open_app(
        self,
        app_name: str,
        screen_num: int = 1,
    ) -> bool:
        """

        Abre una aplicación y, cuando es posible, la coloca en el monitor

        solicitado.



        Args:

            app_name: Nombre/comando de la aplicación.

            screen_num: Monitor de destino.

        """

        try:
            if not app_name or not str(app_name).strip():
                return False

            if screen_num < 1:
                return False

            self.screen_manager.refresh_monitors()

            monitor = self.screen_manager.get_monitor(screen_num)

            if monitor is None:
                logger._print_log(
                    "info", "Procesando solicitud", "app_utils.py", "method", 75
                )

                return False

            app_name = str(app_name).strip()

            logger._print_log(
                "info", "Procesando solicitud", "app_utils.py", "method", 75
            )

            lower_name = app_name.lower()

            if "chrome" in lower_name:
                webbrowser.open("https://www.google.com")

            elif "firefox" in lower_name:
                webbrowser.open("https://www.google.com")

            elif "edge" in lower_name:
                webbrowser.open("https://www.google.com")

            elif "notepad" in lower_name:
                subprocess.Popen(["notepad.exe"])

            elif "calculator" in lower_name or "calculadora" in lower_name:
                subprocess.Popen(["calc.exe"])

            elif "paint" in lower_name:
                subprocess.Popen(["mspaint.exe"])

            else:
                subprocess.Popen(
                    [
                        "cmd",
                        "/c",
                        "start",
                        "",
                        app_name,
                    ],
                    shell=False,
                )

            time.sleep(3)

            # Utilizar la geometría real del monitor.

            return self.screen_manager.move_window_to_monitor(
                app_name,
                screen_num,
            )

        except Exception as e:
            logger._print_log(
                "info", "Procesando solicitud", "app_utils.py", "method", 75
            )

            return False

    # ========================================================================

    # CIERRE

    # ========================================================================

    def close_app(
        self,
        app_name: str,
    ) -> bool:
        """

        Cierra una ventana encontrada para la aplicación.

        """

        try:
            windows = _find_application_windows(app_name)

            if not windows:
                logger.warning(
                    "[APP-MANAGER] No se encontró ventana para %s.",
                    app_name,
                )

                return False

            win = windows[0]

            win.close()

            time.sleep(1)

            logger._print_log(
                "info", "Procesando solicitud", "app_utils.py", "method", 75
            )

            return True

        except Exception as e:
            logger._print_log(
                "info", "Procesando solicitud", "app_utils.py", "method", 75
            )

            return False

    # ========================================================================

    # MOVIMIENTO

    # ========================================================================

    def move_window_to_screen(
        self,
        window_title: str,
        screen_num: int = 1,
    ) -> bool:
        """

        Mueve una ventana a un monitor concreto mediante ScreenManager.

        """

        try:
            if screen_num < 1:
                return False

            self.screen_manager.refresh_monitors()

            if self.screen_manager.get_monitor(screen_num) is None:
                return False

            return self.screen_manager.move_window_to_monitor(
                window_title,
                screen_num,
            )

        except Exception as e:
            logger._print_log(
                "info", "Procesando solicitud", "app_utils.py", "method", 75
            )

            return False

    # ========================================================================

    # CENTRADO

    # ========================================================================

    def center_window(
        self,
        window_title: str,
    ) -> bool:
        """

        Centra una ventana en el monitor donde está situada actualmente.



        No utiliza el escritorio virtual completo como si fuera un monitor.

        """

        try:
            windows = gw.getWindowsWithTitle(window_title)

            if not windows:
                logger._print_log(
                    "info", "Procesando solicitud", "app_utils.py", "method", 75
                )

                return False

            win = windows[0]

            self.screen_manager.refresh_monitors()

            monitor = self._find_monitor_for_window(win)

            if monitor is None:
                logger._print_log(
                    "info", "Procesando solicitud", "app_utils.py", "method", 75
                )

                return False

            monitor_width = int(monitor.width)

            monitor_height = int(monitor.height)

            target_width = min(
                int(win.width),
                max(
                    200,
                    monitor_width - 100,
                ),
            )

            target_height = min(
                int(win.height),
                max(
                    200,
                    monitor_height - 100,
                ),
            )

            x = int(monitor.left + (monitor_width - target_width) // 2)

            y = int(monitor.top + (monitor_height - target_height) // 2)

            x = max(
                int(monitor.left),
                x,
            )

            y = max(
                int(monitor.top),
                y,
            )

            win.moveTo(
                x,
                y,
            )

            try:
                win.resizeTo(
                    target_width,
                    target_height,
                )

            except Exception:
                pass

            logger._print_log(
                "info",
                f"Ventana {window_title} centrada en coordenadas {x}, {y} dentro del monitor %s."
                % (getattr(monitor, "monitor_id", "?")),
                "app_utils.py",
                "center_window",
                296,
            )

            return True

        except Exception as e:
            logger._print_log(
                "info", "Procesando solicitud", "app_utils.py", "method", 75
            )

            return False

    # ========================================================================

    # VERIFICACIÓN

    # ========================================================================

    def verify_app_open(
        self,
        app_name: str,
    ) -> bool:
        """

        Comprueba si existe una ventana visible asociada a la aplicación.

        """

        try:
            windows = _find_application_windows(app_name)

            for win in windows:
                try:
                    if hasattr(
                        win,
                        "is_visible",
                    ):
                        if not bool(win.is_visible):
                            continue

                    return True

                except Exception:
                    continue

            return False

        except Exception as e:
            logger._print_log(
                "error",
                f"Error verificando si la aplicación está abierta: {e}",
                "app_utils.py",
                "verify_app_open",
                349,
            )

            return False

    def _find_monitor_for_window(
        self,
        window: Any,
    ) -> Optional[Any]:
        """

        Determina el monitor en el que se encuentra el centro de una ventana.

        """

        try:
            width = max(
                1,
                int(window.width),
            )

            height = max(
                1,
                int(window.height),
            )

            center_x = int(window.left) + width // 2

            center_y = int(window.top) + height // 2

            for monitor in self.screen_manager.monitors:
                try:
                    if monitor.contains_point(
                        center_x,
                        center_y,
                    ):
                        return monitor

                except Exception:
                    continue

        except Exception:
            pass

        return None


# ============================================================================

# SINGLETON / FACTORY

# ============================================================================


def get_app_manager() -> AppManager:
    """

    Obtiene una instancia del gestor de aplicaciones.

    """

    return AppManager()


# ============================================================================

# DETECCIÓN VISUAL

# ============================================================================


def analyze_elements_in_screenshot(
    screenshot_path: str,
    app_name: str,
) -> List[Dict[str, Any]]:
    """

    Analiza una captura mediante Vision/Qwen3-VL.



    El formato devuelto es:



        [

            {

                "name": "...",

                "type": "...",

                "bbox": [x1, y1, x2, y2],

                "center": [x, y],

                "confidence": 0.95,

                ...

            }

        ]



    Las coordenadas devueltas por Vision son relativas a la imagen analizada.



    Esta función es una utilidad y no forma parte del flujo principal de

    CalibrationManager.

    """

    if not screenshot_path:
        return []

    path = Path(screenshot_path)

    if not path.exists():
        logger._print_log("info", "Procesando solicitud", "app_utils.py", "method", 75)

        return []

    prompt = f"""

Analiza exclusivamente la interfaz visible de la aplicación

"{app_name}".



Detecta elementos interactivos visibles:

- botones

- campos de entrada

- menús

- enlaces

- pestañas

- checkboxes

- radios

- selectores

- iconos interactivos

- controles visibles



No incluyas:

- escritorio

- barra de tareas

- otras aplicaciones

- elementos puramente decorativos

- elementos no visibles



Devuelve únicamente JSON válido:



{{

  "elements": [

    {{

      "name": "nombre_semantico",

      "type": "button",

      "bbox": [x1, y1, x2, y2],

      "confidence": 0.95

    }}

  ]

}}



Las coordenadas bbox deben estar normalizadas entre 0 y 1000

respecto a toda la imagen.



Máximo 80 elementos.

"""

    try:
        vision = Vision(model="qwen3-vl:8b-instruct")

        analysis_result = vision.analyze_image(
            str(path),
            prompt,
        )

        data = _extract_json(analysis_result)

        if not isinstance(data, dict):
            return []

        raw_elements = data.get(
            "elements",
            [],
        )

        if not isinstance(
            raw_elements,
            list,
        ):
            return []

        elements: List[Dict[str, Any]] = []

        for item in raw_elements:
            if not isinstance(item, dict):
                continue

            name = str(
                item.get(
                    "name",
                    "",
                )
            ).strip()

            element_type = (
                str(
                    item.get(
                        "type",
                        "other",
                    )
                )
                .strip()
                .lower()
            )

            bbox = _normalize_bbox(item.get("bbox"))

            if not name or bbox is None:
                continue

            confidence = _safe_confidence(
                item.get(
                    "confidence",
                    0.0,
                )
            )

            elements.append(
                {
                    "name": name,
                    "type": element_type,
                    "bbox": bbox,
                    "confidence": confidence,
                }
            )

        logger._print_log(
            "debug",
            f"Análisis visual completado para {app_name}: {len(elements)} elementos",
            "app_utils.py",
            "analyze_elements_in_screenshot",
            559,
        )

        return elements

    except Exception as e:
        logger._print_log(
            "error",
            f"Error analizando la captura de {app_name}: {e}",
            "app_utils.py",
            "analyze_elements_in_screenshot",
            568,
        )

        # Importante:

        # no devolvemos coordenadas inventadas.

        return []


# ============================================================================

# JSON

# ============================================================================


def _extract_json(
    response: str,
) -> Any:
    """

    Extrae JSON incluso si Vision devuelve un bloque Markdown.

    """

    text = str(response or "").strip()

    if not text:
        raise ValueError("Respuesta vacía")

    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        pass

    start_candidates = [
        text.find("{"),
        text.find("["),
    ]

    start_candidates = [value for value in start_candidates if value >= 0]

    if not start_candidates:
        raise ValueError("No se encontró JSON en la respuesta")

    start = min(start_candidates)

    opener = text[start]

    closer = "}" if opener == "{" else "]"

    depth = 0

    in_string = False

    escaped = False

    for index in range(
        start,
        len(text),
    ):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True

        elif char == opener:
            depth += 1

        elif char == closer:
            depth -= 1

            if depth == 0:
                candidate = text[start : index + 1]

                return json.loads(candidate)

    raise ValueError("JSON incompleto")


# ============================================================================

# BBOX

# ============================================================================


def _normalize_bbox(
    bbox: Any,
) -> Optional[List[float]]:
    """

    Valida bbox normalizada 0..1000.

    """

    if not isinstance(
        bbox,
        (list, tuple),
    ):
        return None

    if len(bbox) < 4:
        return None

    try:
        values = [
            float(bbox[0]),
            float(bbox[1]),
            float(bbox[2]),
            float(bbox[3]),
        ]

    except (
        TypeError,
        ValueError,
    ):
        return None

    if not all(0.0 <= value <= 1000.0 for value in values):
        return None

    x1, y1, x2, y2 = values

    if x2 <= x1:
        return None

    if y2 <= y1:
        return None

    return values


def _safe_confidence(
    value: Any,
) -> float:
    """

    Normaliza confidence a 0..1.

    """

    try:
        value = float(value)

    except (
        TypeError,
        ValueError,
    ):
        return 0.0

    return max(
        0.0,
        min(
            1.0,
            value,
        ),
    )


# ============================================================================

# VENTANAS

# ============================================================================


def _find_application_windows(
    app_name: str,
) -> List[Any]:
    """

    Busca ventanas mediante varios nombres/patrones comunes.

    """

    name = str(app_name or "").strip()

    if not name:
        return []

    patterns = [name]

    lower_name = name.lower()

    aliases = {
        "chrome": [
            "Google Chrome",
            "Chrome",
            "Google",
        ],
        "edge": [
            "Microsoft Edge",
            "Microsoft",
            "Edge",
        ],
        "firefox": [
            "Mozilla Firefox",
            "Mozilla",
            "Firefox",
        ],
        "notepad": [
            "Notepad",
            "Bloc de notas",
        ],
        "calculator": [
            "Calculator",
            "Calculadora",
        ],
        "paint": [
            "Paint",
            "mspaint",
        ],
        "explorer": [
            "File Explorer",
            "Explorador de archivos",
            "Explorer",
        ],
        "cmd": [
            "Command Prompt",
            "Símbolo del sistema",
            "cmd",
        ],
    }

    for key, values in aliases.items():
        if key in lower_name:
            patterns.extend(values)

    result: List[Any] = []

    for pattern in patterns:
        try:
            windows = gw.getWindowsWithTitle(pattern)

            for win in windows:
                if win not in result:
                    result.append(win)

        except Exception:
            continue

    return result


# ============================================================================

# COMPATIBILIDAD

# ============================================================================


def open_app_on_screen(
    app_name: str,
    screen_num: int = 1,
) -> bool:
    """

    Abre una aplicación en un monitor.

    """

    return get_app_manager().open_app(
        app_name,
        screen_num,
    )


def close_app(
    app_name: str,
) -> bool:
    """

    Cierra una aplicación.

    """

    return get_app_manager().close_app(app_name)


def move_window_to_screen(
    window_title: str,
    screen_num: int = 1,
) -> bool:
    """

    Mueve una ventana a un monitor.

    """

    return get_app_manager().move_window_to_screen(
        window_title,
        screen_num,
    )


def center_window(
    window_title: str,
) -> bool:
    """

    Centra una ventana dentro de su monitor actual.

    """

    return get_app_manager().center_window(window_title)
