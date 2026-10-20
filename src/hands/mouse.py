# src/hands/mouse.py
"""
Control básico del ratón para JARVIS.
"""

from __future__ import annotations

import time
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


def move_to_position(x: float, y: float, duration: float = 0.1) -> bool:
    """
    Mueve el ratón a una posición específica.
    
    Args:
        x: Coordenada X
        y: Coordenada Y  
        duration: Duración del movimiento en segundos
        
    Returns:
        True si tuvo éxito, False si falló
    """
    try:
        # Validar coordenadas
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            logger._print_log("error", f"Coordenadas inválidas: ({x}, {y})", "mouse.py", "move_to_position", 183)
            return False
        
        # Ejecutar movimiento
        import pyautogui
        pyautogui.moveTo(int(x), int(y), duration=float(duration))
        return True
        
    except Exception as e:
        logger._print_log("error", f"Error al mover ratón: {e}", "mouse.py", "move_to_position", 192)
        return False


def click_element(button: str = "left", wait_after: float = 0.1) -> bool:
    """
    Realiza un clic con el ratón.
    
    Args:
        button: Botón a usar (left, right, middle)
        wait_after: Tiempo de espera después del clic
        
    Returns:
        True si tuvo éxito, False si falló
    """
    try:
        import pyautogui
        
        # Validar botón
        button = button.lower()
        if button not in ["left", "right", "middle"]:
            logger._print_log("error", f"Botón no válido: '{button}'. Valores permitidos: left, right, middle.", "mouse.py", "click_element", 210)
            return False
        
        # Ejecutar clic
        pyautogui.click(button=button)
        time.sleep(wait_after)
        return True
        
    except Exception as e:
        logger._print_log("error", f"Error al hacer clic: {e}", "mouse.py", "click_element", 221)
        return False


def scroll_at_position(x: float, y: float, clicks: int, wait_after: float = 0.1) -> bool:
    """
    Realiza scroll en una posición específica.
    
    Args:
        x: Coordenada X
        y: Coordenada Y
        clicks: Número de clicks de scroll (positivo para arriba, negativo para abajo)
        wait_after: Tiempo de espera después del scroll
        
    Returns:
        True si tuvo éxito, False si falló
    """
    try:
        # Validar coordenadas
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            logger._print_log("error", f"Coordenadas inválidas: ({x}, {y})", "mouse.py", "scroll_at_position", 238)
            return False
        
        # Validar botón
        if not isinstance(clicks, int):
            logger._print_log("error", f"Clicks inválidos: {clicks}", "mouse.py", "scroll_at_position", 243)
            return False
        
        # Ejecutar scroll
        import pyautogui
        pyautogui.scroll(clicks, x=int(x), y=int(y))
        time.sleep(wait_after)
        return True
        
    except Exception as e:
        logger._print_log("error", f"Error al hacer scroll: {e}", "mouse.py", "scroll_at_position", 252)
        return False


# Registrar capacidades básicas
def register_mouse_capabilities():
    """Registra las capacidades del ratón en el sistema."""
    try:
        from src.hands.action_registry import get_action_registry, register_action
        
        registry = get_action_registry()
        
        # Registrar capacidades básicas
        register_action("move_mouse", "Mover ratón a posición", "INTERACTION")(move_to_position)
        register_action("click_mouse", "Hacer clic con el ratón", "INTERACTION")(click_element)
        register_action("scroll_mouse", "Hacer scroll con el ratón", "INTERACTION")(scroll_at_position)
        
        logger._print_log("info", "Capacidades del ratón registradas exitosamente", "mouse.py", "register_mouse_capabilities", 267)
        
    except Exception as e:
        logger._print_log("error", f"Error al registrar capacidades del ratón: {e}", "mouse.py", "register_mouse_capabilities", 272)


# Inicializar capacidades al importar
register_mouse_capabilities()