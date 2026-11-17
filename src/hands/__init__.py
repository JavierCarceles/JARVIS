# src/hands/__init__.py
from src.hands.actions.executor import Executor
from src.hands.actions.action_registry import get_action_registry, register_action, register_module, ActionType
from src.hands.calibration.calibration_manager import get_calibration_manager, CalibrationManager
from src.hands.calibration.coordinate_manager import get_coordinate_manager, CoordinateManager
from src.hands.apps.applications_core import get_application_manager, get_applications_by_capability, register_custom_application
from src.hands.browsers import chrome
from src.hands.input import keyboard  
from src.hands.input import mouse

# Importar y registrar modulos de aplicaciones
from src.hands.browsers import chrome

__all__ = [
    'Executor', 
    'get_action_registry', 
    'register_action', 
    'register_module',
    'ActionType',
    'get_calibration_manager',
    'CalibrationManager',
    'get_coordinate_manager',
    'CoordinateManager',
    'get_application_manager',
    'get_applications_by_capability',
    'register_custom_application',
    'chrome',
    'keyboard',
    'mouse'
]