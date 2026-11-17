# src/hands/input/mouse.py
"""
Control basico del raton para JARVIS.

Las funciones publicas (``move_to_position``, ``click_element``,
``scroll_at_position``) y las acciones registradas (``move_mouse``,
``click_mouse``, ``scroll_mouse``) usan el contrato de plataforma de escritorio
(``src.desktop.platform_contract.get_desktop_platform``):

* Las coordenadas son las del escritorio nativo del SO (Windows:
  ``DESKTOP_PIXELS``; macOS: ``DESKTOP_POINTS``). El posicionamiento es absoluto
  y se comprueba leyendo la posicion real del puntero despues de moverlo.
* ``click_element`` mueve el puntero al destino (absoluto), lee su posicion
  real, comprueba la ventana y el control bajo el puntero y aborta (sin hacer
  clic) si la diferencia supera la tolerancia medida. El DPI/CPI del raton y
  la aceleracion no son factores de escala de pantalla.
* Si el SO no tiene adaptador o la operacion no esta soportada, se usa
  pyautogui como respaldo. Un fallo real del adaptador (sesion bloqueada,
  permiso ausente, UIPI) NO se oculta con el respaldo: se devuelve ``False``.
* Proteccion de emergencia: si ``keyboard.fail_safe_enabled`` esta activo en
  ``config.json`` y el puntero esta en una esquina del monitor principal, la
  operacion se cancela (equivalente al FAILSAFE de pyautogui).
"""

from __future__ import annotations

import time
from typing import Any, Optional

from src.core.log import get_logger
from src.desktop.platform_contract import DESKTOP_PIXELS
from src.hands.calibration.coordinate_spaces import (
    CoordinateSpace,
    PointerVerifier,
    SpaceBox,
    SpacePoint,
)

logger = get_logger(__name__)

# Codigos de error del contrato que permiten usar el respaldo pyautogui.
_FALLBACK_CODES = ("not_supported", "dependency_missing")


def _desktop_platform() -> Optional[Any]:
    """Adaptador de escritorio del SO actual o None si no existe."""
    try:
        from src.desktop.platform_contract import get_desktop_platform

        return get_desktop_platform()
    except Exception as exc:  # PlatformNotSupportedError u otro fallo de carga
        logger.debug("Sin adaptador de escritorio, se usara pyautogui: %s", exc)
        return None


def _can_fallback(result: Any) -> bool:
    error = getattr(result, "error", None)
    code = getattr(getattr(error, "code", None), "value", None)
    return code in _FALLBACK_CODES


def _failsafe_triggered(adapter: Any) -> bool:
    """True si el puntero esta en una esquina del monitor principal y el
    failsafe de config.json esta activo."""
    try:
        from src.core.config import get_keyboard_config

        if not bool(getattr(get_keyboard_config(), "fail_safe_enabled", False)):
            return False
        position = adapter.get_pointer_position()
        displays = adapter.enumerate_displays()
        if not position.ok or not displays.ok or not displays.value:
            return False
        primary = next((d for d in displays.value if d.is_primary), displays.value[0])
        b = primary.bounds
        corners = (
            (b.left, b.top),
            (b.right - 1, b.top),
            (b.left, b.bottom - 1),
            (b.right - 1, b.bottom - 1),
        )
        px, py = int(round(position.value.x)), int(round(position.value.y))
        return any(px == int(round(cx)) and py == int(round(cy)) for cx, cy in corners)
    except Exception as exc:
        logger.debug("No se pudo evaluar el failsafe del raton: %s", exc)
        return False


def move_to_position(x: float, y: float, duration: float = 0.1) -> bool:
    """
    Mueve el raton a una posicion absoluta del escritorio.

    Args:
        x: Coordenada X (espacio de escritorio nativo del SO)
        y: Coordenada Y
        duration: Duracion del movimiento en segundos. Solo se aplica con el
            respaldo pyautogui; el adaptador posiciona de forma absoluta.

    Returns:
        True si el puntero quedo en la posicion pedida, False si fallo
    """
    try:
        # Validar coordenadas
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            logger.error("Coordenadas invalidas: (%s, %s)", x, y)
            return False

        adapter = _desktop_platform()
        if adapter is not None:
            if _failsafe_triggered(adapter):
                logger.warning("Failsafe del raton activado: puntero en una esquina del monitor principal")
                return False
            result = adapter.move_pointer(float(x), float(y))
            if result.ok:
                error_px = result.details.get("error_px", 0)
                if error_px and error_px > 1:
                    logger.warning(
                        "El puntero quedo a %s px de la posicion pedida (%s, %s)", error_px, x, y
                    )
                    return False
                return True
            if not _can_fallback(result):
                logger.error("No se pudo mover el raton: %s", result.error)
                return False

        # Respaldo: SO sin adaptador o operacion no soportada.
        import pyautogui
        pyautogui.moveTo(int(x), int(y), duration=float(duration))
        return True

    except Exception as e:
        logger.error("Error al mover raton: %s", e)
        return False


def click_element(
    button: str = "left",
    wait_after: float = 0.1,
    x: Optional[float] = None,
    y: Optional[float] = None,
    window_id: Optional[int] = None,
    pid: Optional[int] = None,
    expected_box: Optional[SpaceBox] = None,
    pixels_per_unit: float = 1.0,
    tolerance_px: Optional[float] = None,
    tolerance_ratio: Optional[float] = None,
) -> bool:
    """
    Realiza un clic con el raton tras verificar el puntero.

    Antes de cada clic: mueve el puntero al destino (posicionamiento absoluto),
    lee su posicion real, comprueba la ventana y el control bajo el puntero y
    aborta (sin hacer clic) si la diferencia supera la tolerancia medida. El
    DPI/CPI del raton y la aceleracion no son factores de escala de pantalla.

    Args:
        button: Boton a usar (left, right, middle)
        wait_after: Tiempo de espera despues del clic
        x: Coordenada X absoluta del escritorio en espacio nativo del SO
        y: Coordenada Y absoluta del escritorio en espacio nativo del SO
        window_id: ID de ventana esperado bajo el puntero
        pid: ID de proceso esperado de la ventana bajo el puntero
        expected_box: Caja esperada del control, en espacio de escritorio
        pixels_per_unit: Pixeles de escritorio por unidad (error a pixeles)
        tolerance_px: Tolerancia absoluta de posicion en pixeles
        tolerance_ratio: Tolerancia relativa al lado menor de la caja esperada

    Returns:
        True si se verifico el puntero y se hizo clic, False si se aborto
    """
    try:
        # Validar boton
        button = button.lower()
        if button not in ["left", "right", "middle"]:
            logger.error("Boton no valido: '%s'. Valores permitidos: left, right, middle.", button)
            return False

        adapter = _desktop_platform()

        # Respaldo: SO sin adaptador o operacion no soportada.
        if adapter is None:
            import pyautogui

            pyautogui.click(button=button)
            time.sleep(wait_after)
            return True

        if _failsafe_triggered(adapter):
            logger.warning("Failsafe del raton activado: clic cancelado")
            return False

        desktop_space = CoordinateSpace.from_value(
            getattr(adapter, "desktop_space", DESKTOP_PIXELS)
        )

        # Destino del clic: el pedido o la posicion real actual del puntero.
        if x is not None and y is not None:
            target = SpacePoint(float(x), float(y), desktop_space)
        else:
            position = adapter.get_pointer_position()
            if not position.ok or position.value is None:
                logger.error(
                    "No se pudo leer la posicion real del puntero: %s", position.error
                )
                return False
            pos = position.value
            target = SpacePoint(float(pos.x), float(pos.y), desktop_space)

        # Verificacion de puntero antes del clic: mueve el puntero
        # (posicionamiento absoluto), lee su posicion real, comprueba la
        # tolerancia, la ventana y el control bajo el puntero; aborta si se
        # excede la tolerancia medida. Nunca hace clic si la verificacion
        # falla.
        verifier = PointerVerifier(
            adapter=adapter,
            tolerance_px=tolerance_px,
            tolerance_ratio=0.15 if tolerance_ratio is None else float(tolerance_ratio),
            default_tolerance_units=1.5,
            require_foreground=window_id is not None,
        )
        verification = verifier.move_and_verify(
            target,
            expected_window_id=window_id,
            expected_pid=pid,
            expected_box=expected_box,
            pixels_per_unit=float(pixels_per_unit or 1.0),
        )
        if not verification.ok:
            logger.warning(
                "Clic abortado por verificacion de puntero: %s (error_px=%s, ventana_ok=%s, elemento_ok=%s)",
                verification.reason,
                verification.error_px,
                verification.window_ok,
                verification.element_ok,
            )
            return False

        click_result = adapter.click(button=button, count=1)
        if not click_result.ok:
            if not _can_fallback(click_result):
                logger.error("No se pudo hacer clic: %s", click_result.error)
                return False
            import pyautogui

            pyautogui.click(button=button)

        time.sleep(wait_after)
        return True

    except Exception as e:
        logger.error("Error al hacer clic: %s", e)
        return False


def scroll_at_position(x: float, y: float, clicks: int, wait_after: float = 0.1) -> bool:
    """
    Realiza scroll en una posicion especifica.
    
    Args:
        x: Coordenada X
        y: Coordenada Y
        clicks: Numero de clicks de scroll (positivo para arriba, negativo para abajo)
        wait_after: Tiempo de espera despues del scroll
        
    Returns:
        True si tuvo exito, False si fallo
    """
    try:
        # Validar coordenadas
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            logger.error(f"Coordenadas invalidas: ({x}, {y})")
            return False
        
        # Validar clicks de rueda
        if not isinstance(clicks, int):
            logger.error("Clicks invalidos: %s", clicks)
            return False

        adapter = _desktop_platform()
        if adapter is not None:
            if not move_to_position(x, y):
                return False
            # Cada click es una muesca de rueda (positivo hacia arriba).
            result = adapter.scroll(clicks)
            if result.ok:
                time.sleep(wait_after)
                return True
            if not _can_fallback(result):
                logger.error("No se pudo hacer scroll: %s", result.error)
                return False

        # Respaldo: SO sin adaptador o operacion no soportada.
        import pyautogui
        pyautogui.scroll(clicks, x=int(x), y=int(y))
        time.sleep(wait_after)
        return True

    except Exception as e:
        logger.error("Error al hacer scroll: %s", e)
        return False


# Registrar capacidades basicas
def register_mouse_capabilities():
    """Registra las capacidades del raton en el sistema."""
    try:
        from src.hands.actions.action_registry import get_action_registry, register_action
        
        registry = get_action_registry()
        
        # Registrar capacidades basicas
        register_action("move_mouse", "Mover rat\u00f3n a posici\u00f3n", "INTERACTION")(move_to_position)
        register_action("click_mouse", "Hacer clic con el rat\u00f3n", "INTERACTION")(click_element)
        register_action("scroll_mouse", "Hacer scroll con el rat\u00f3n", "INTERACTION")(scroll_at_position)
        
        logger.info("Capacidades del raton registradas exitosamente")
        
    except Exception as e:
        logger.error(f"Error al registrar capacidades del raton: {e}")


# Inicializar capacidades al importar
register_mouse_capabilities()