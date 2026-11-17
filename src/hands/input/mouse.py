# src/hands/input/mouse.py
"""
Control basico del raton para JARVIS.
"""

from __future__ import annotations

import time
from typing import Optional

from src.core.log import get_logger

logger = get_logger(__name__)


def move_to_position(x: float, y: float, duration: float = 0.1) -> bool:
    """
    Mueve el raton a una posicion especifica.
    
    Args:
        x: Coordenada X
        y: Coordenada Y  
        duration: Duracion del movimiento en segundos
        
    Returns:
        True si tuvo exito, False si fallo
    """
    try:
        # Validar coordenadas
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            logger.error(f"Coordenadas invalidas: ({x}, {y})")
            return False
        
        # Ejecutar movimiento
        import pyautogui
        pyautogui.moveTo(int(x), int(y), duration=float(duration))
        return True
        
    except Exception as e:
        logger.error(f"Error al mover raton: {e}")
        return False


def click_element(button: str = "left", wait_after: float = 0.1) -> bool:
    """
    Realiza un clic con el raton.
    
    Args:
        button: Boton a usar (left, right, middle)
        wait_after: Tiempo de espera despues del clic
        
    Returns:
        True si tuvo exito, False si fallo
    """
    try:
        import pyautogui
        
        # Validar boton
        button = button.lower()
        if button not in ["left", "right", "middle"]:
            logger.error(f"Boton no valido: '{button}'. Valores permitidos: left, right, middle.")
            return False
        
        # Ejecutar clic
        pyautogui.click(button=button)
        time.sleep(wait_after)
        return True
        
    except Exception as e:
        logger.error(f"Error al hacer clic: {e}")
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
        
        # Validar boton
        if not isinstance(clicks, int):
            logger.error(f"Clicks invalidos: {clicks}")
            return False
        
        # Ejecutar scroll
        import pyautogui
        pyautogui.scroll(clicks, x=int(x), y=int(y))
        time.sleep(wait_after)
        return True
        
    except Exception as e:
        logger.error(f"Error al hacer scroll: {e}")
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