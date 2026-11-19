# -*- coding: ascii -*-
"""
Fixture de calibracion GUI multiplataforma (tests/fixtures/gui_calibration_app/).

Aplicacion de escritorio real escrita con Qt/PySide6 que se ejecuta en Windows
y macOS y expone arbol de accesibilidad nativo en ambos SO. Sirve de objetivo
controlado y con verdad-terreno para medir la precision del motor de
calibracion/deteccion de JARVIS (pipeline accesibilidad -> vision -> fusion).

Cada control expone:
  - identificador estable (objectName / accessibleName)
  - geometria de referencia (referencia en coordenadas del area cliente)
  - accion inocua instrumentada (solo incrementa un contador, sin efectos
    secundarios sobre el equipo ni datos del usuario)

Incluye un control dibujado a mano SIN accesibilidad para verificar que los
detectores no lo marcan como accionable por falsos positivos.

La verdad-terreno (geometria de referencia y recuento de acciones) se expone
por un canal separado (archivo JSON en runtime/) que el detector evaluado no
consume (ver unidad 3.8.6.10.2).
"""

from .app import CalibrationAppWindow
from .controls import CONTROL_SPECS, CONTROL_BY_ID
from .truth_ground import TruthGround, get_truth_ground

__all__ = [
    "CalibrationAppWindow",
    "CONTROL_SPECS",
    "CONTROL_BY_ID",
    "TruthGround",
    "get_truth_ground",
]
