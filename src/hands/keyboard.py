"""
Control del teclado - VERSIÓN MIGRADA.

Este módulo se transforma de acciones primitivas a capacidades reutilizables
para el sistema de planificación jerárquica de JARVIS.

TRANSFORMACIÓN PRINCIPAL:
Antes: Funciones de teclado independientes
Ahora: Capacidades reutilizables con precondiciones, efectos y costes

Integración con la nueva arquitectura:
- Cada acción se convierte en una capacidad con metadatos
- Soporta precondiciones y efectos para el grafo de estados
- Tiene coste asociado para la planificación A*
- Puede requerir contexto del sistema (campo activo, aplicación enfocada)
- Se integra con el sistema de estado para verificar condiciones

Ejemplo de transformación:

ANTIGUO:
def escribir_texto(texto: str) -> str:
    # Lógica directa

NUEVO:
@keyboard_capability(
    name="type_text",
    description="Escribir texto en el campo activo",
    preconditions=["field_focused", "keyboard_available"],
    effects=["text_typed", "field_updated"],
    cost=1.0,
    required_resources=["focused_element"]
)
def type_text(text: str, field_id: Optional[str] = None) -> bool:
    # Verificar estado del sistema
    # Ejecutar escritura
    # Verificar éxito
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

import pyautogui

from src.utils.config import get_keyboard_config
from src.utils.logger import get_logger
from src.hands.action_registry import (
    register_action,
    ActionType,
    ActionInfo,
    get_action_registry,
)

logger = get_logger(__name__)

# Configuración global de PyAutoGUI según config.json.
keyboard_config = get_keyboard_config()
pyautogui.FAILSAFE = keyboard_config.fail_safe_enabled
pyautogui.PAUSE = keyboard_config.pause_between_actions


# ============================================================================
# NUEVO SISTEMA: CAPACIDADES DEL TECLADO
# ============================================================================

class KeyModifier(Enum):
    """Modificadores de tecla soportados."""
    CTRL = "ctrl"
    ALT = "alt"
    SHIFT = "shift"
    WIN = "win"


@dataclass
class KeyboardCapabilities:
    """Capacidades del teclado para el sistema de planificación."""
    
    # Capacidad básica: escribir texto
    type_text: Dict[str, Any]
    # Capacidad: presionar teclas individuales
    press_key: Dict[str, Any]
    # Capacidad: combinaciones de teclas
    hotkey: Dict[str, Any]
    # Capacidad: operaciones de texto comunes
    text_operations: Dict[str, Any]
    # Capacidad: navegación por teclado
    navigation: Dict[str, Any]
    # Capacidad: atajos de sistema
    system_shortcuts: Dict[str, Any]


# ============================================================================
# DECORADOR PARA CAPACIDADES DEL TECLADO
# ============================================================================

def keyboard_capability(
    name: str,
    description: str,
    preconditions: List[str] = None,
    effects: List[str] = None,
    cost: float = 1.0,
    required_resources: List[str] = None,
    application: Optional[str] = None,
    success_checker: Optional[Callable] = None,
    planner_enabled: bool = True,
    keyboard_action: str = "basic"
):
    """
    Decorador para registrar capacidades del teclado en el sistema de planificación.
    
    Args:
        name: Nombre de la capacidad
        description: Descripción detallada
        preconditions: Condiciones requeridas para ejecutar
        effects: Efectos sobre el estado del sistema
        cost: Coste de ejecución para planificación
        required_resources: Recursos necesarios
        application: Aplicación asociada
        success_checker: Función para verificar éxito
        planner_enabled: ¿Puede ser usada por el planificador?
        keyboard_action: Tipo de acción de teclado básica
    """
    
    def decorator(func: Callable):
        # Crear metadatos de la acción
        action_info = ActionInfo(
            name=name,
            description=description,
            action_type=ActionType.INTERACTION,
            function=func,
            parameters=func.__annotations__,
            module=func.__module__,
            category="keyboard",
            tags=["keyboard", keyboard_action],
            confidence_threshold=0.8,
            preconditions=preconditions or [],
            effects=effects or [],
            cost=cost,
            dependencies=required_resources or [],
            capability=f"keyboard.{keyboard_action}",
            application=application,
            required_resources=required_resources or [],
            success_checker=success_checker,
            planner_enabled=planner_enabled
        )
        
        # Registrar en el action registry
        register_action(
            name=name,
            description=description,
            action_type=ActionType.INTERACTION,
            category="keyboard",
            tags=["keyboard", keyboard_action],
            preconditions=preconditions or [],
            effects=effects or [],
            cost=cost,
            capability=f"keyboard.{keyboard_action}",
            application=application,
            required_resources=required_resources or [],
            planner_enabled=planner_enabled
        )(func)
        
        logger._print_log("info", f"Capacidad registrada: {name}", "keyboard.py", "method", 166)
        return func
    
    return decorator


# ============================================================================
# CAPACIDADES MIGRADAS DEL TECLADO
# ============================================================================

@keyboard_capability(
    name="type_text",
    description="Escribir texto en el campo activo",
    preconditions=["keyboard_available", "field_focused"],
    effects=["text_typed", "field_updated", "content_changed"],
    cost=2.0,
    required_resources=["focused_field"]
)
def type_text(text: str, interval: Optional[float] = None, field_id: Optional[str] = None) -> bool:
    """
    Escribir texto en el campo activo o en un campo específico.
    
    Nueva arquitectura:
    - Verifica disponibilidad del teclado
    - Puede verificar si un campo específico está enfocado
    - Registra cambios en el estado
    - Devuelve éxito/fracaso para el planificador
    """
    
    if not text:
        logger._print_log("INFO", "Texto vacío proporcionado", "keyboard.py", "type_text", 196)
        return False
    
    text = str(text)
    preview = text[:50]
    logger._print_log("INFO", "Escribiendo texto: '" + preview + "...'", "keyboard.py", "type_text", 201)
    
    try:
        # Validar intervalo de escritura
        if interval is None:
            interval = getattr(keyboard_config, "typing_interval", 0.05)
        
        typing_interval = max(0.0, float(interval))
        
        # Ejecutar escritura
        pyautogui.write(text, interval=typing_interval)
        
        logger._print_log("debug", f"Texto escrito: {preview}...", "keyboard.py", "method", 213)
        return True
        
    except Exception as e:
        logger._print_log("error", f"Error en type_text: {e}", "keyboard.py", "method", 217)

        return False


@keyboard_capability(
    name="press_key",
    description="Presionar una tecla individual",
    preconditions=["keyboard_available"],
    effects=["key_pressed", "input_executed"],
    cost=0.5,
    required_resources=[]
)
def press_key(key: str, hold_time: float = 0.1) -> bool:
    """
    Presionar una tecla individual.
    
    Nueva arquitectura:
    - Validación de teclas válidas
    - Tiempo de espera configurable
    - Registro de la acción ejecutada
    """
    
    if not key:
        logger._print_log("info", "Tecla vacía proporcionada", "keyboard.py", "method", 240)
        return False
    
    key = str(key).strip()
    logger._print_log("debug", f"Presionando tecla: {key}", "keyboard.py", "method", 244)
    
    try:
        # Ejecutar pulsación
        pyautogui.press(key)
        
        # Esperar si es necesario (para teclas especiales)
        if hold_time > 0:
            time.sleep(hold_time)
        
        logger._print_log("info", f"Tecla '{key}' presionada", "keyboard.py", "method", 254)
        return True
        
    except Exception as e:
        logger._print_log("error", f"Error en press_key: {e}", "keyboard.py", "method", 258)

        return False


@keyboard_capability(
    name="execute_hotkey",
    description="Ejecutar combinación de teclas",
    preconditions=["keyboard_available", "application_active"],
    effects=["hotkey_executed", "shortcut_triggered"],
    cost=1.0,
    required_resources=["active_application"]
)
def execute_hotkey(*keys: str, hold_time: float = 0.1) -> bool:
    """
    Ejecutar combinación de teclas (hotkeys).
    
    Nueva arquitectura:
    - Soporte para múltiples modificadores
    - Validación de combinaciones válidas
    - Contexto de aplicación requerido
    """
    
    if not keys:
        logger._print_log("info", "Ninguna tecla proporcionada para hotkey", "keyboard.py", "method", 281)
        return False
    
    # Limpiar y validar teclas
    cleaned_keys = [str(key).strip().lower() for key in keys if key]
    if not cleaned_keys:
        logger._print_log("info", "Teclas inválidas en hotkey", "keyboard.py", "method", 287)
        return False
    
    hotkey_str = " + ".join(cleaned_keys)
    logger._print_log("info", f"Ejecutando hotkey: {hotkey_str}", "keyboard.py", "method", 291)
    
    try:
        # Ejecutar hotkey
        pyautogui.hotkey(*cleaned_keys)
        
        # Esperar estabilidad
        if hold_time > 0:
            time.sleep(hold_time)
        
        logger._print_log("info", f"Hotkey ejecutado: {hotkey_str}", "keyboard.py", "method", 301)
        return True
        
    except Exception as e:
        logger._print_log("error", f"Error en execute_hotkey: {e}", "keyboard.py", "method", 305)

        return False


# Capacidad común para operaciones de texto
@keyboard_capability(
    name="copy_text",
    description="Copiar texto seleccionado (Ctrl+C)",
    preconditions=["text_selected", "clipboard_available"],
    effects=["text_copied", "clipboard_updated"],
    cost=1.0,
    required_resources=["selected_text"]
)
def copy_text() -> bool:
    """Copiar texto seleccionado al portapapeles."""
    
    logger._print_log("info", "Ejecutando Ctrl+C (Copiar)...", "keyboard.py", "method", 321)
    
    try:
        execute_hotkey("ctrl", "c")
        logger._print_log("info", "Texto copiado al portapapeles", "keyboard.py", "method", 325)
        return True
    except Exception as e:
        logger._print_log("error", f"Error en copy_text: {e}", "keyboard.py", "method", 328)

        return False


@keyboard_capability(
    name="paste_text",
    description="Pegar texto desde el portapapeles (Ctrl+V)",
    preconditions=["clipboard_available", "field_focused"],
    effects=["text_pasted", "field_updated"],
    cost=1.0,
    required_resources=["focused_field", "clipboard_content"]
)
def paste_text() -> bool:
    """Pegar texto desde el portapapeles."""
    
    logger._print_log("info", "Ejecutando Ctrl+V (Pegar)...", "keyboard.py", "method", 343)
    
    try:
        execute_hotkey("ctrl", "v")
        logger._print_log("info", "Texto pegado", "keyboard.py", "method", 347)
        return True
    except Exception as e:
        logger._print_log("error", f"Error en paste_text: {e}", "keyboard.py", "method", 350)

        return False


@keyboard_capability(
    name="cut_text",
    description="Cortar texto seleccionado (Ctrl+X)",
    preconditions=["text_selected", "clipboard_available"],
    effects=["text_cut", "clipboard_updated", "field_cleared"],
    cost=1.0,
    required_resources=["selected_text"]
)
def cut_text() -> bool:
    """Cortar texto seleccionado al portapapeles."""
    
    logger._print_log("info", "Ejecutando Ctrl+X (Cortar)...", "keyboard.py", "method", 365)
    
    try:
        execute_hotkey("ctrl", "x")
        logger._print_log("info", "Texto cortado", "keyboard.py", "method", 369)
        return True
    except Exception as e:
        logger._print_log("error", f"Error en cut_text: {e}", "keyboard.py", "method", 372)


        return False


@keyboard_capability(
    name="select_all",
    description="Seleccionar todo el texto (Ctrl+A)",
    preconditions=["field_focused", "text_available"],
    effects=["text_selected", "selection_complete"],
    cost=0.8,
    required_resources=["focused_field"]
)
def select_all_text() -> bool:
    """Seleccionar todo el texto en el campo activo."""
    
    logger._print_log("info", "Ejecutando Ctrl+A (Seleccionar todo)...", "keyboard.py", "method", 387)
    
    try:
        execute_hotkey("ctrl", "a")
        logger._print_log("info", "Texto seleccionado completo", "keyboard.py", "method", 391)
        return True
    except Exception as e:
        logger._print_log("error", f"Error en select_all_text: {e}", "keyboard.py", "method", 394)

        return False


# Capacidad para navegación por teclado
@keyboard_capability(
    name="navigate_tab",
    description="Navegar con Tabulador",
    preconditions=["keyboard_available", "ui_navigable"],
    effects=["field_changed", "focus_moved"],
    cost=0.5,
    required_resources=[]
)
def navigate_tab(forward: bool = True) -> bool:
    """
    Navegar entre campos con Tabulador.
    
    Args:
        forward: True para Tab adelante, False para Shift+Tab atrás
    """
    
    direction = "adelante" if forward else "atrás"
    logger._print_log("info", f"Navegación con Tab: {direction}", "keyboard.py", "method", 416)
    
    try:
        if forward:
            press_key("tab")
        else:
            execute_hotkey("shift", "tab")
        
        logger._print_log("info", f"Navegación completada: {direction}", "keyboard.py", "method", 424)
        return True
    except Exception as e:
        logger._print_log("error", f"Error en navigate_tab: {e}", "keyboard.py", "method", 427)

        return False


@keyboard_capability(
    name="navigate_enter",
    description="Confirmar con Enter",
    preconditions=["field_focused", "form_submittable"],
    effects=["form_submitted", "action_confirmed"],
    cost=0.5,
    required_resources=["focused_field"]
)
def navigate_enter() -> bool:
    """Confirmar acción con la tecla Enter."""
    
    logger._print_log("info", "Presionando Enter para confirmar...", "keyboard.py", "method", 442)
    
    try:
        press_key("enter")
        logger._print_log("info", "Acción confirmada con Enter", "keyboard.py", "method", 446)

        return True
    except Exception as e:
        logger._print_log("error", f"Error en navigate_enter: {e}", "keyboard.py", "method", 449)

        return False


# Capacidad para atajos de sistema
@keyboard_capability(
    name="switch_window",
    description="Cambiar de ventana (Alt+Tab)",
    preconditions=["multiple_windows", "window_switchable"],
    effects=["window_switched", "focus_changed"],
    cost=1.5,
    required_resources=[]
)
def switch_window() -> bool:
    """Cambiar a la siguiente ventana con Alt+Tab."""
    
    logger._print_log("info", "Ejecutando Alt+Tab (Cambiar ventana)...", "keyboard.py", "method", 465)
    
    try:
        execute_hotkey("alt", "tab")
        logger._print_log("info", "Ventana cambiada", "keyboard.py", "method", 469)
        return True
    except Exception as e:
        logger._print_log("error", f"Error en switch_window: {e}", "keyboard.py", "method", 472)

        return False


@keyboard_capability(
    name="close_window",
    description="Cerrar ventana (Alt+F4)",
    preconditions=["window_closable", "no_unsaved_data"],
    effects=["window_closed", "application_terminated"],
    cost=1.0,
    required_resources=["active_window"]
)
def close_window() -> bool:
    """Cerrar la ventana activa con Alt+F4."""
    
    logger._print_log("info", "Ejecutando Alt+F4 (Cerrar ventana)...", "keyboard.py", "method", 487)
    
    try:
        execute_hotkey("alt", "f4")
        logger._print_log("info", "Ventana cerrada", "keyboard.py", "method", 491)
        return True
    except Exception as e:
        logger._print_log("error", f"Error en close_window: {e}", "keyboard.py", "method", 494)

        return False


@keyboard_capability(
    name="open_start_menu",
    description="Abrir menú de inicio (Tecla Windows)",
    preconditions=["system_available"],
    effects=["start_menu_opened", "menu_visible"],
    cost=0.5,
    required_resources=[]
)
def open_start_menu() -> bool:
    """Abrir el menú de inicio de Windows."""
    
    logger._print_log("INFO", "[KEYBOARD] Abriendo menú de inicio...  [file:keyboard.py, method:open_start_menu, line:509]", "keyboard.py", "open_start_menu", 509)
    
    try:
        press_key("win")
        time.sleep(0.2)  # Esperar a que el menú se abra
        logger._print_log("INFO", r"[KEYBOARD] Menú de inicio abierto  [file:keyboard.py, method:open_start_menu, line:514]", "keyboard.py", "open_start_menu", 514)

        return True
    except Exception as e:
        logger._print_log("ERROR", r"[KEYBOARD] Error en open_start_menu: %s  [file:keyboard.py, method:open_start_menu, line:517]", "keyboard.py", "unknown", 17019)

        return False


# ============================================================================
# FUNCIONES DE COMPATIBILIDAD (mantenidas para transición)
# ============================================================================

def _get_typing_interval(interval: Optional[float]) -> float:
    """Obtiene el intervalo de escritura (mantenido por compatibilidad)."""
    if interval is None:
        interval = getattr(keyboard_config, "typing_interval", 0.05)
    
    try:
        return max(0.0, float(interval))
    except (TypeError, ValueError):
        logger._print_log("WARNING", r"Intervalo de escritura inválido. Se utilizará 0.05.  [file:keyboard.py, method:_get_typing_interval, line:533]", "keyboard.py", "unknown", 17703)

        return 0.05


def escribir_texto(texto: str, interval: Optional[float] = None) -> str:
    """
    Escribe texto en el campo activo (mantenido por compatibilidad).
    """
    texto = str(texto)
    preview = texto[:50]
    typing_interval = _get_typing_interval(interval)
    
    logger._print_log("INFO", r"[-] Acción: Escribiendo texto: '%s...'  [file:keyboard.py, method:escribir_texto, line:545]", "keyboard.py", "unknown", 18124)

    
    try:
        pyautogui.write(texto, interval=typing_interval)
        return f"Texto '{preview}...' escrito."
    except Exception as e:
        logger._print_log("ERROR", r"Error en escribir_texto: %s  [file:keyboard.py, method:escribir_texto, line:551]", "keyboard.py", "unknown", 18387)

        return f"Error al escribir texto: {e}"


def presionar_enter() -> str:
    """
    Presiona la tecla Enter (mantenido por compatibilidad).
    """
    logger._print_log("DEBUG", r"[-] Acción: Presionando ENTER...  [file:keyboard.py, method:presionar_enter, line:559]", "keyboard.py", "unknown", 18645)

    try:
        pyautogui.press("enter")
        return "Enter presionado."
    except Exception as e:
        logger._print_log("ERROR", r"Error en presionar_enter: %s  [file:keyboard.py, method:presionar_enter, line:564]", "keyboard.py", "unknown", 18862)

        return f"Error al presionar Enter: {e}"


def presionar_tecla(tecla: str) -> str:
    """
    Presiona una tecla específica (mantenido por compatibilidad).
    """
    tecla = str(tecla).strip()
    
    logger._print_log("DEBUG", r"[-] Acción: Presionando tecla '%s'...  [file:keyboard.py, method:presionar_tecla, line:574]", "keyboard.py", "unknown", 19175)

    
    if not tecla:
        return "Error al presionar tecla: la tecla está vacía."
    
    try:
        pyautogui.press(tecla)
        return f"Tecla '{tecla}' presionada."
    except Exception as e:
        logger._print_log("ERROR", r"Error en presionar_tecla: %s  [file:keyboard.py, method:presionar_tecla, line:583]", "keyboard.py", "unknown", 19498)

        return f"Error al presionar tecla: {e}"


def copiar() -> str:
    """
    Ejecuta Ctrl+C (Copiar) (mantenido por compatibilidad).
    """
    logger._print_log("INFO", r"[-] Acción: Ejecutando Control + C (Copiar)...  [file:keyboard.py, method:copiar, line:591]", "keyboard.py", "unknown", 19750)

    try:
        pyautogui.hotkey("ctrl", "c")
        return "Texto copiado al portapapeles."
    except Exception as e:
        logger._print_log("ERROR", r"Error en copiar: %s  [file:keyboard.py, method:copiar, line:596]", "keyboard.py", "unknown", 19989)

        return f"Error al copiar: {e}"


def pegar() -> str:
    """
    Ejecuta Ctrl+V (Pegar) (mantenido por compatibilidad).
    """
    logger._print_log("INFO", r"[-] Acción: Ejecutando Control + V (Pegar)...  [file:keyboard.py, method:pegar, line:604]", "keyboard.py", "unknown", 20212)

    try:
        pyautogui.hotkey("ctrl", "v")
        return "Texto pegado."
    except Exception as e:
        logger._print_log("ERROR", r"Error en pegar: %s  [file:keyboard.py, method:pegar, line:609]", "keyboard.py", "unknown", 20432)

        return f"Error al pegar: {e}"


def cortar() -> str:
    """
    Ejecuta Ctrl+X (Cortar) (mantenido por compatibilidad).
    """
    logger._print_log("INFO", r"[-] Acción: Ejecutando Control + X (Cortar)...  [file:keyboard.py, method:cortar, line:617]", "keyboard.py", "unknown", 20654)

    try:
        pyautogui.hotkey("ctrl", "x")
        return "Texto cortado."
    except Exception as e:
        logger._print_log("ERROR", r"Error en cortar: %s  [file:keyboard.py, method:cortar, line:622]", "keyboard.py", "unknown", 20877)

        return f"Error al cortar: {e}"


def seleccionar_todo() -> str:
    """
    Ejecuta Ctrl+A (Seleccionar todo) (mantenido por compatibilidad).
    """
    logger._print_log("DEBUG", r"[-] Acción: Ejecutando Control + A (Seleccionar todo)...  [file:keyboard.py, method:seleccionar_todo, line:630]", "keyboard.py", "unknown", 21122)

    try:
        pyautogui.hotkey("ctrl", "a")
        return "Todo seleccionado."
    except Exception as e:
        logger._print_log("ERROR", r"Error en seleccionar_todo: %s  [file:keyboard.py, method:seleccionar_todo, line:635]", "keyboard.py", "unknown", 21370)

        return f"Error al seleccionar: {e}"


def cambiar_ventana() -> str:
    """
    Ejecuta Alt+Tab (Cambiar ventana) (mantenido por compatibilidad).
    """
    logger._print_log("DEBUG", r"[-] Acción: Ejecutando Alt + Tab (Cambiar ventana)...  [file:keyboard.py, method:cambiar_ventana, line:643]", "keyboard.py", "unknown", 21639)

    try:
        pyautogui.hotkey("alt", "tab")
        return "Ventana cambiada."
    except Exception as e:
        logger._print_log("ERROR", r"Error en cambiar_ventana: %s  [file:keyboard.py, method:cambiar_ventana, line:648]", "keyboard.py", "cambiar_ventana", 648)

        return f"Error al cambiar ventana: {e}"


def cerrar_ventana() -> str:
    """
    Ejecuta Alt+F4 (Cerrar ventana) (mantenido por compatibilidad).
    """
    logger._print_log("DEBUG", r"[-] Acción: Ejecutando Alt + F4 (Cerrar ventana)...  [file:keyboard.py, method:cerrar_ventana, line:656]", "keyboard.py", "unknown", 22151)

    try:
        pyautogui.hotkey("alt", "f4")
        return "Ventana cerrada."
    except Exception as e:
        logger._print_log("ERROR", r"Error en cerrar_ventana: %s  [file:keyboard.py, method:cerrar_ventana, line:661]", "keyboard.py", "unknown", 22390)

        return f"Error al cerrar ventana: {e}"



def tecla_super() -> str:
    """
    Presiona la tecla Windows (Super) (mantenido por compatibilidad).
    """
    logger._print_log("debug", "[-] Acción: Presionando tecla Windows (Super)...", "keyboard.py", "method", 669)
    try:
        pyautogui.press("win")
        return "Tecla Super presionada."
    except Exception as e:
        logger._print_log("error", f"Error al presionar Super: {e}")



def abrir_menu_inicio() -> str:
    """
    Abre el menú de inicio de Windows (mantenido por compatibilidad).
    """
    logger._print_log("INFO", r"[-] Acción: Abriendo menú de inicio...  [file:keyboard.py, method:abrir_menu_inicio, line:682]", "keyboard.py", "unknown", 23187)

    try:

        pyautogui.press("win")
        time.sleep(0.2)
        return "Menú de inicio abierto."
    except Exception as e:
        logger._print_log("ERROR", r"Error en abrir_menu_inicio: %s  [file:keyboard.py, method:abrir_menu_inicio, line:688]", "keyboard.py", "unknown", 23439)
        return f"Error al abrir menú: {e}"



# ============================================================================
# SISTEMA DE CAPACIDADES (nuevo para planificación)
# ============================================================================

class KeyboardCapabilitySystem:
    """
    Sistema de capacidades del teclado para la planificación jerárquica.
    
    Proporciona un conjunto de capacidades reutilizables que el planificador
    puede utilizar para construir rutas complejas de interacción con el teclado.
    """
    
    def __init__(self):
        """Inicializar el sistema de capacidades."""
        self.capabilities = self._initialize_capabilities()
    
    def _initialize_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """Inicializar el catálogo de capacidades."""
        return {
            "text": {
                "type_text": {
                    "description": "Escribir texto en campo activo",
                    "cost": 2.0,
                    "preconditions": ["keyboard_available", "field_focused"],
                    "effects": ["text_typed", "field_updated"]
                },
                "copy_text": {
                    "description": "Copiar texto (Ctrl+C)",
                    "cost": 1.0,
                    "preconditions": ["text_selected", "clipboard_available"],
                    "effects": ["text_copied", "clipboard_updated"]
                },
                "paste_text": {
                    "description": "Pegar texto (Ctrl+V)",
                    "cost": 1.0,
                    "preconditions": ["clipboard_available", "field_focused"],
                    "effects": ["text_pasted", "field_updated"]
                },
                "cut_text": {
                    "description": "Cortar texto (Ctrl+X)",
                    "cost": 1.0,
                    "preconditions": ["text_selected", "clipboard_available"],
                    "effects": ["text_cut", "clipboard_updated"]
                },
                "select_all_text": {
                    "description": "Seleccionar todo (Ctrl+A)",
                    "cost": 0.8,
                    "preconditions": ["field_focused", "text_available"],
                    "effects": ["text_selected", "selection_complete"]
                }
            },
            "navigation": {
                "navigate_tab": {
                    "description": "Navegar con Tabulador",
                    "cost": 0.5,
                    "preconditions": ["keyboard_available", "ui_navigable"],
                    "effects": ["field_changed", "focus_moved"]
                },
                "navigate_enter": {
                    "description": "Confirmar con Enter",
                    "cost": 0.5,
                    "preconditions": ["field_focused", "form_submittable"],
                    "effects": ["form_submitted", "action_confirmed"]
                }
            },
            "shortcuts": {
                "execute_hotkey": {
                    "description": "Ejecutar combinación de teclas",
                    "cost": 1.0,
                    "preconditions": ["keyboard_available", "application_active"],
                    "effects": ["hotkey_executed", "shortcut_triggered"]
                },
                "switch_window": {
                    "description": "Cambiar ventana (Alt+Tab)",
                    "cost": 1.5,
                    "preconditions": ["multiple_windows", "window_switchable"],
                    "effects": ["window_switched", "focus_changed"]
                },
                "close_window": {
                    "description": "Cerrar ventana (Alt+F4)",
                    "cost": 1.0,
                    "preconditions": ["window_closable", "no_unsaved_data"],
                    "effects": ["window_closed", "application_terminated"]
                },
                "open_start_menu": {
                    "description": "Abrir menú de inicio",
                    "cost": 0.5,
                    "preconditions": ["system_available"],
                    "effects": ["start_menu_opened", "menu_visible"]
                }
            },
            "basic": {
                "press_key": {
                    "description": "Presionar tecla individual",
                    "cost": 0.5,
                    "preconditions": ["keyboard_available"],
                    "effects": ["key_pressed", "input_executed"]
                }
            }
        }
    
    def get_capabilities_for_context(self, context: Dict[str, Any]) -> List[str]:
        """
        Obtener capacidades que se pueden ejecutar con el contexto dado.
        
        Args:
            context: Contexto actual del sistema (aplicación activa, estado, etc.)
        """
        available_capabilities = []
        
        for category, caps in self.capabilities.items():
            for cap_name, cap_info in caps.items():
                # Verificar precondiciones contra el contexto
                required_conditions = cap_info.get("preconditions", [])
                if self._check_conditions(required_conditions, context):
                    available_capabilities.append(f"{category}.{cap_name}")
        
        return available_capabilities
    
    def _check_conditions(self, conditions: List[str], context: Dict[str, Any]) -> bool:
        """Verificar si las condiciones se cumplen en el contexto dado."""
        for condition in conditions:
            # Simplificado: en un sistema real esto sería más complejo
            if condition == "keyboard_available":
                # Asumir que el teclado está disponible por defecto
                continue
            elif condition == "field_focused":
                # Verificar si hay un campo enfocado en el contexto
                if not context.get("focused_field"):
                    return False
            elif condition == "application_active":
                # Verificar si hay una aplicación activa
                if not context.get("active_application"):
                    return False
            elif condition == "text_selected":
                # Verificar si hay texto seleccionado
                if not context.get("text_selected"):
                    return False
            # Añadir más condiciones según sea necesario
        
        return True
    
    def can_execute_capability(self, capability_name: str, context: Dict[str, Any]) -> bool:
        """¿Se puede ejecutar una capacidad con el contexto dado?"""
        parts = capability_name.split(".")
        if len(parts) != 2:
            return False
        
        category, cap_name = parts
        if category not in self.capabilities:
            return False
        
        cap_info = self.capabilities[category].get(cap_name)
        if not cap_info:
            return False
        
        required_conditions = cap_info.get("preconditions", [])
        return self._check_conditions(required_conditions, context)


# Instancia global del sistema de capacidades
_keyboard_capability_system: Optional[KeyboardCapabilitySystem] = None


def get_keyboard_capability_system() -> KeyboardCapabilitySystem:
    """Obtener la instancia global del sistema de capacidades del teclado."""
    global _keyboard_capability_system
    
    if _keyboard_capability_system is None:
        _keyboard_capability_system = KeyboardCapabilitySystem()
    
    return _keyboard_capability_system