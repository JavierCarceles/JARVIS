# -*- coding: ascii -*-
"""
Punto de entrada para lanzar la fixture de calibracion GUI como proceso
independiente (subprocess).

Uso:
    python tests/fixtures/gui_calibration_app/run.py

La ventana se abre segun la variante configurada por variables de entorno
(unidad 3.8.6.10.4):
    FIXTURE_ESTADO_VENTANA = maximizada | restaurada
    FIXTURE_TEMA           = claro | oscuro
    FIXTURE_TAMANIO_FUENTE = <entero>
    FIXTURE_ZOOM_INTERNO   = <flotante>
    FIXTURE_MENU_ABIERTO   = 1 | 0
    FIXTURE_SCROLL_DESPLAZADO = 1 | 0
    FIXTURE_CONTROL_DINAMICO_VISIBLE = 1 | 0

Al iniciarse escribe la verdad-terreno de referencia en runtime/ y mantiene
actualizado el recuento de acciones a medida que se interactua con los
controles. Es el objetivo controlado de las pruebas GUI reales de calibracion.
"""

import os
import sys

# Garantiza que las importaciones absolutas con prefijo del paquete funcionen
# al lanzar este fichero directamente como script.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ_TESTS = os.path.dirname(os.path.dirname(_AQUI))
if _RAIZ_TESTS not in sys.path:
    sys.path.insert(0, _RAIZ_TESTS)
if os.path.dirname(_RAIZ_TESTS) not in sys.path:
    sys.path.insert(0, os.path.dirname(_RAIZ_TESTS))

from tests.fixtures.gui_calibration_app.app import crear_aplicacion


def main():
    app, ventana = crear_aplicacion()
    config = ventana.config
    if config.estado_ventana == "maximizada":
        ventana.showMaximized()
    else:
        ventana.resize(1200, 800)
        ventana.show()
    app.exec()


if __name__ == "__main__":
    main()
