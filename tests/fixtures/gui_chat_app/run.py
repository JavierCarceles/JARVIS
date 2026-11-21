# -*- coding: ascii -*-
"""
Lanza la aplicacion de chat de prueba como proceso independiente.

Uso:
    python tests/fixtures/gui_chat_app/run.py
Registro de eventos: variable de entorno JARVIS_CHAT_FIXTURE_EVENTOS.
"""

import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(_AQUI)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from tests.fixtures.gui_chat_app.app import crear_aplicacion  # noqa: E402


def main() -> int:
    app, _ventana = crear_aplicacion()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
