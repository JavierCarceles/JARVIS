# src/hands/__init__.py
from .executor import Executor
from .action_registry import get_action_registry, register_action, register_module, ActionType
from .calibration_manager import get_calibration_manager, CalibrationManager
from .coordinate_manager import get_coordinate_manager, CoordinateManager
from .applications_core import get_application_manager, get_applications_by_capability, register_custom_application
from . import chrome
from . import keyboard  
from . import mouse

# Importar y registrar módulos de aplicaciones
from . import chrome

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