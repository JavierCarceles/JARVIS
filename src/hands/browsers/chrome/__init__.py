"""
Modulo especifico para Google Chrome con sistema de acciones registrado.
"""

# Importar y registrar acciones de Chrome
from src.hands.browsers.chrome.chrome import abrir_chrome, abrir_chrome_pantalla, _abrir_chrome_desde_ruta, _verificar_chrome_abierto, _verificar_chrome_instalado, _capturar_chrome, get_chrome_commands

# Importar calibrador de Chrome
from src.hands.browsers.chrome.chrome_calibrator import ChromeCalibrator, calibrar_chrome

# Registrar el modulo completo en el sistema de acciones
from src.hands.actions.action_registry import register_module, register_action
from src.hands.actions.action_registry import ActionType

# Registrar acciones individuales con el nuevo sistema
@register_action(
    name="abrir_chrome",
    description="Abre Google Chrome en el navegador",
    action_type= ActionType.APPLICATION,
    category="navegacion",
    tags=["chrome", "web", "navegador"]
)
def abrir_chrome_action():
    """Accion wrapper para abrir Chrome."""
    return abrir_chrome()

@register_action(
    name="abrir_chrome_pantalla",
    description="Abre Google Chrome en una pantalla espec\u00edfica",
    action_type=ActionType.APPLICATION,
    category="navegacion",
    tags=["chrome", "multi-monitor", "pantalla"]
)
def abrir_chrome_pantalla_action(pantalla: int = 1):
    """Accion wrapper para abrir Chrome en pantalla especifica."""
    return abrir_chrome_pantalla(pantalla)

@register_action(
    name="calibrar_chrome",
    description="Calibra Google Chrome con sistema mejorado y nombres sem\u00e1nticos",
    action_type=ActionType.APPLICATION,
    category="calibracion",
    tags=["chrome", "calibracion", "qwen3vl", "multi-monitor"]
)
def calibrar_chrome_action():
    """Accion wrapper para calibrar Chrome."""
    return calibrar_chrome()

# Registrar el modulo completo
register_module("src.hands.browsers.chrome")

# Exportar componentes principales
__all__ = [
    # Chrome basico
    'abrir_chrome',
    'abrir_chrome_pantalla', 
    'get_chrome_commands',
    
    # Calibradores
    'ChromeCalibrator',
    'calibrar_chrome',
    
    # Acciones registradas
    'abrir_chrome_action',
    'abrir_chrome_pantalla_action',
    'calibrar_chrome_action'
]