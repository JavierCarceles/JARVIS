"""

Calibrador manual de la macro riot_api.

El calibrador registra coordenadas absolutas del escritorio y las guarda

asociadas al monitor real (s1, s2, ...). La topología, posición y resolución

de los monitores se obtienen de config/config.json mediante ScreenManager.

Este módulo es específico de la calibración manual de la macro riot_api.

No modifica otras macros ni otras calibraciones existentes.

"""

from __future__ import annotations
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from src.utils.logger import get_logger

logger = get_logger(__name__)
import pyautogui
from src.utils.config import get_project_root
from src.utils.screen_manager import MonitorInfo, get_screen_manager

PASOS = (
    "BOTÓN LOGIN",
    "CHECKBOX CAPTCHA ('No soy un robot')",
    "ESQUINA SUPERIOR IZQUIERDA (CAPTCHA)",
    "ESQUINA SUPERIOR DERECHA (CAPTCHA)",
    "ESQUINA INFERIOR DERECHA (CAPTCHA)",
    "ESQUINA INFERIOR IZQUIERDA (CAPTCHA)",
    "BOTÓN GENERATE API KEY",
    "BOTÓN COPY",
)

IDLE_SECONDS = 2.0
POLL_INTERVAL = 0.1
POST_CAPTURE_DELAY = 0.5


def _get_macros_coords_path() -> Path:
    """

    Obtiene la ruta de macros_coords.json.

    La ubicación habitual del proyecto es data/macros_coords.json.

    Se mantiene compatibilidad con un macros_coords.json en la raíz.

    """
    project_root = Path(get_project_root())
    preferred = project_root / "data" / "macros_coords.json"
    if preferred.exists():
        return preferred
    root_file = project_root / "macros_coords.json"
    if root_file.exists():
        return root_file
    # Para una primera ejecución, la ruta canónica sigue siendo data/.
    return preferred


def _screen_key(monitor: MonitorInfo) -> str:
    """Convierte el ID lógico del monitor a la clave sN del JSON."""
    return f"s{int(monitor.monitor_id)}"


def _format_monitor(monitor: MonitorInfo) -> str:
    """Devuelve una descripción legible del monitor."""
    return (
        f"Monitor {monitor.monitor_id} "
        f"({monitor.name or monitor.device_name or 'sin nombre'}) "
        f"pos=({monitor.left},{monitor.top}) "
        f"size={monitor.width}x{monitor.height}"
    )


def _get_monitor_for_screen_number(
    screen_number: Optional[int],
) -> Optional[MonitorInfo]:
    """Obtiene un monitor configurado por su número lógico 1-based."""
    if screen_number is None:
        return None
    try:
        monitor = get_screen_manager().get_monitor(int(screen_number))
    except Exception as exc:
        logger.warning(
            "[RIOT-CALIBRATOR] No se pudo obtener el monitor %s: %s", screen_number, exc
        )
        return None
    if monitor is None:
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
    return monitor


def _detect_monitor_from_mouse() -> Optional[MonitorInfo]:
    """Obtiene el monitor que contiene actualmente el puntero."""
    try:
        x, y = pyautogui.position()
        monitor = get_screen_manager().get_monitor_by_point(int(x), int(y))
        if monitor is None:
            logger.warning(
                "[RIOT-CALIBRATOR] El puntero (%s,%s) está fuera de "
                "los monitores definidos en config.json.",
                x,
                y,
            )
        return monitor
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        return None


def _capture_point_on_monitor(
    monitor: MonitorInfo,
    paso: str,
    paso_index: int,
) -> Optional[Tuple[int, int]]:
    """

    Espera a que el ratón permanezca quieto IDLE_SECONDS sobre el monitor.

    La posición devuelta es absoluta y nativa, tal como la necesita

    macros_coords.json.

    """
    logger.info(
        "[RIOT-CALIBRATOR] Iniciando paso %s en %s", paso, _format_monitor(monitor)
    )
    logger.info(
        f"Paso {paso_index + 1}/{len(PASOS)}: {paso}\n"
        f"  Coloca el ratón en el punto correcto del {_screen_key(monitor)} "
        f"y mantenlo quieto {IDLE_SECONDS:.0f} segundos."
    )
    last_pos = pyautogui.position()
    stable_since = time.monotonic()
    while True:
        current_pos = pyautogui.position()
        if current_pos != last_pos:
            last_pos = current_pos
            stable_since = time.monotonic()
        current_monitor = get_screen_manager().get_monitor_by_point(
            int(current_pos[0]),
            int(current_pos[1]),
        )
        # Evitamos mezclar coordenadas de otro monitor durante la misma
        # calibración. El usuario debe mantener todos los puntos en el
        # monitor elegido.
        if current_monitor is None:
            stable_since = time.monotonic()
            time.sleep(POLL_INTERVAL)
            continue
        if current_monitor.monitor_id != monitor.monitor_id:
            stable_since = time.monotonic()
            logger.warning(
                "[RIOT-CALIBRATOR] El ratón está en %s, pero se esperaba %s.",
                _screen_key(current_monitor),
                _screen_key(monitor),
            )
            time.sleep(POLL_INTERVAL)
            continue
        if time.monotonic() - stable_since >= IDLE_SECONDS:
            x, y = int(current_pos[0]), int(current_pos[1])
            logger.info(f"[CAPTURADO] ({paso}): ({x}, {y}) -> {_screen_key(monitor)}")
            time.sleep(POST_CAPTURE_DELAY)
            return x, y
        time.sleep(POLL_INTERVAL)


def _calculate_capture_region(
    corners: Dict[str, Tuple[int, int]],
) -> Optional[list[int]]:
    """

    Calcula [x, y, ancho, alto] usando las cuatro esquinas.

    Se utiliza la esquina superior izquierda como origen y las diferencias

    geométricas entre las esquinas para determinar el tamaño.

    """
    required = ("tl", "tr", "br", "bl")
    if any(key not in corners for key in required):
        return None
    tl = corners["tl"]
    tr = corners["tr"]
    br = corners["br"]
    bl = corners["bl"]
    left = min(tl[0], tr[0], br[0], bl[0])
    top = min(tl[1], tr[1], br[1], bl[1])
    right = max(tl[0], tr[0], br[0], bl[0])
    bottom = max(tl[1], tr[1], br[1], bl[1])
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        return None
    return [left, top, width, height]


def _build_calibration_data(
    points: Dict[str, Tuple[int, int]],
    capture_region: Optional[list[int]],
) -> Dict[str, object]:
    """Construye el bloque de datos de calibración."""
    result: Dict[str, object] = {
        "login": list(points["login"]),
        "captcha": list(points["captcha"]),
        "generate": list(points["generate"]),
        "copy": list(points["copy"]),
    }
    if capture_region is not None:
        result["capture_regions"] = capture_region
    return result


def imprimir_resultados(
    datos: Dict[str, object],
    screen_key: Optional[str] = None,
) -> None:
    """Muestra por consola los datos capturados."""
    logger.info("RESULTADOS DE CALIBRACIÓN RIOT_API")
    if screen_key:
        logger.info("Monitor: %s", screen_key)
    for key in ("login", "captcha", "generate", "copy", "capture_regions"):
        if key in datos:
            logger.info("  %s: %s", key, datos[key])


def _load_json(ruta_json: Path) -> Dict[str, object]:
    """Carga el JSON existente o crea una estructura raíz vacía."""
    if not ruta_json.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de coordenadas: {ruta_json}"
        )
    with ruta_json.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("macros_coords.json debe contener un objeto JSON.")
    return data


def _atomic_write_json(ruta_json: Path, data: Dict[str, object]) -> None:
    """Escribe el JSON de forma atómica para evitar archivos incompletos."""
    ruta_json.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{ruta_json.stem}_",
        suffix=".tmp",
        dir=str(ruta_json.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
            )
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, ruta_json)
    except Exception:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def gestionar_json(
    nuevos_datos: Dict[str, object],
    screen_key: str,
    ruta_json: Optional[Path] = None,
) -> bool:
    """

    Actualiza únicamente riot_api para el monitor indicado.

    No borra otras macros, otras pantallas ni otras calibraciones.

    """
    if ruta_json is None:
        ruta_json = _get_macros_coords_path()
    logger.info(
        "[RIOT-CALIBRATOR] Guardando calibración en %s | monitor=%s",
        ruta_json,
        screen_key,
    )
    try:
        config = _load_json(ruta_json)
        macros = config.setdefault("macros", {})
        if not isinstance(macros, dict):
            raise ValueError("La propiedad 'macros' debe ser un objeto JSON.")
        riot_api = macros.setdefault("riot_api", {})
        if not isinstance(riot_api, dict):
            raise ValueError("La propiedad 'macros.riot_api' debe ser un objeto JSON.")
        # Cada elemento queda asociado al monitor al que pertenece.
        for key in ("login", "captcha", "generate", "copy"):
            if key not in nuevos_datos:
                continue
            element = riot_api.setdefault(key, {})
            if not isinstance(element, dict):
                element = {}
                riot_api[key] = element
            element[screen_key] = nuevos_datos[key]
        if "capture_regions" in nuevos_datos:
            regions = riot_api.setdefault("capture_regions", {})
            if not isinstance(regions, dict):
                regions = {}
                riot_api["capture_regions"] = regions
            regions[screen_key] = nuevos_datos["capture_regions"]
        backup_path = ruta_json.with_suffix(ruta_json.suffix + ".bak")
        if ruta_json.exists():
            try:
                backup_path.write_bytes(ruta_json.read_bytes())
            except Exception as exc:
                logger.warning(
                    "[RIOT-CALIBRATOR] No se pudo crear backup %s: %s",
                    backup_path,
                    exc,
                )
        _atomic_write_json(ruta_json, config)
        logger.info(
            "[RIOT-CALIBRATOR] Calibración guardada correctamente en %s",
            ruta_json,
        )
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        return True
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        return False


def calibrar_api_key_riot_macro(
    screen_number: Optional[int] = None,
) -> bool:
    """

    Ejecuta la calibración manual de riot_api.

    Args:

        screen_number:

            Número lógico 1-based del monitor. Cuando es None, se detecta

            automáticamente el monitor donde está el ratón al iniciar.

    Returns:

        True si la calibración y guardado finalizan correctamente.

    """
    screen_manager = get_screen_manager()
    if screen_number is not None:
        monitor = _get_monitor_for_screen_number(screen_number)
    else:
        monitor = _detect_monitor_from_mouse()
    if monitor is None:
        logger.error(
            "No se pudo determinar el monitor de calibración. Comprueba la configuración de config.json."
        )
        return False
    logger._print_log(
        "info", "--- CALIBRADOR RIOT_API ACTIVADO ---", "get_coords.py", "method", 413
    )
    logger.info(
        f"Monitor seleccionado: {_format_monitor(monitor)} -> {_screen_key(monitor)}"
    )
    logger.info(
        "La calibración no pide elegir s1/s2 manualmente: "
        "la pantalla se obtiene de config.json y de la posición del ratón."
    )
    logger.info(
        f"Coloca el ratón en cada punto y mantenlo quieto {IDLE_SECONDS:.0f} segundos."
    )
    logger._print_log(
        "info", "Pulsa Ctrl+C para abortar.\n", "get_coords.py", "method", 426
    )
    puntos: Dict[str, Tuple[int, int]] = {}
    esquinas: Dict[str, Tuple[int, int]] = {}
    try:
        for paso_index, paso in enumerate(PASOS):
            punto = _capture_point_on_monitor(
                monitor=monitor,
                paso=paso,
                paso_index=paso_index,
            )
            if punto is None:
                logger._print_log(
                    "info", "Procesando solicitud", "get_coords.py", "method", 97
                )
                return False
            if paso_index == 0:
                puntos["login"] = punto
            elif paso_index == 1:
                puntos["captcha"] = punto
            elif paso_index == 2:
                esquinas["tl"] = punto
            elif paso_index == 3:
                esquinas["tr"] = punto
            elif paso_index == 4:
                esquinas["br"] = punto
            elif paso_index == 5:
                esquinas["bl"] = punto
            elif paso_index == 6:
                puntos["generate"] = punto
            elif paso_index == 7:
                puntos["copy"] = punto
        capture_region = _calculate_capture_region(esquinas)
        datos = _build_calibration_data(
            points=puntos,
            capture_region=capture_region,
        )
        screen_key = _screen_key(monitor)
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        logger.info("CALIBRACIÓN COMPLETADA")
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        imprimir_resultados(datos, screen_key=screen_key)
        return gestionar_json(
            nuevos_datos=datos,
            screen_key=screen_key,
        )
    except KeyboardInterrupt:
        logger.info("Calibración abortada por el usuario.")
        logger._print_log(
            "info",
            "[RIOT-CALIBRATOR] Calibración abortada con Ctrl+C.",
            "get_coords.py",
            "method",
            488,
        )
        return False
    except Exception as exc:
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        logger._print_log("info", "Procesando solicitud", "get_coords.py", "method", 97)
        return False


def calibrarApiKeyRiotMacro(
    screen_number: Optional[int] = None,
) -> bool:
    """Alias compatible con la función histórica del proyecto."""
    return calibrar_api_key_riot_macro(screen_number=screen_number)


if __name__ == "__main__":
    calibrar_api_key_riot_macro()
