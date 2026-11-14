# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.3.

Comprueba contra el SO real que JARVIS detecta cuando una aplicacion ya esta
abierta y reutiliza la instancia existente en vez de lanzar un proceso nuevo.

Verificacion a nivel de proceso (tasklist del SO real):
* ``notepad.exe``: el usuario puede tenerlo ya abierto; ese proceso es ajeno y
  nunca se toca. La prueba lanza su propio proceso, lo cuenta, lo termina y
  compara antes y despues.
* ``mspaint.exe`` (Paint): camino negativo real, sin tocar ningun proceso.

No se mueve ni cierra ninguna ventana del usuario. La ventana que aparezca
incidentalmente pertenece al proceso de notepad del usuario y se deja intacta.
"""

import subprocess
import time
import unittest
from unittest.mock import patch

from src.hands.applications_core import ApplicationManager, open_application

_NOTEPAD = "notepad.exe"


def _contar_procesos(nombre_ejecutable: str) -> int:
    """Cuenta procesos con ese nombre de imagen en tasklist del SO real."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {nombre_ejecutable}"],
        capture_output=True,
        text=True,
        check=False,
    )
    lineas = (resultado.stdout or "").splitlines()
    return sum(
        1 for linea in lineas if nombre_ejecutable.lower() in linea.lower()
    )


class TestAplicacionYaAbiertaEntornoReal(unittest.TestCase):
    """3.8.5.3: comprobar si la aplicacion ya esta abierta y reutilizarla."""

    def setUp(self):
        self.manager = ApplicationManager()
        self.conteo_notepad_inicial = _contar_procesos(_NOTEPAD)
        self.proc = None

    def tearDown(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def _esperar_conteo_notepad(self, esperado, timeout_segundos=10.0):
        fin = time.time() + timeout_segundos
        while time.time() < fin:
            if _contar_procesos(_NOTEPAD) == esperado:
                return True
            time.sleep(0.25)
        return False

    def test_3_8_5_3_1_deteccion_tiempo_real_abierto_y_cerrado(self):
        # Camino negativo real: Paint no esta en ejecucion y no se lanza nada.
        self.assertFalse(self.manager.is_application_open("Paint"))

        # Estado inicial de Notepad refleja la realidad del SO
        # (puede ser >= 1 por proceso del usuario; ese proceso es ajeno).
        self.assertEqual(
            self.manager.is_application_open("Notepad"),
            self.conteo_notepad_inicial > 0,
        )

        # Lanzamos nuestro propio proceso Notepad (solo su PID; lo terminamos al final).
        self.proc = subprocess.Popen([_NOTEPAD])
        self.assertIsNotNone(self.proc.pid)
        esperado = self.conteo_notepad_inicial + 1
        self.assertTrue(
            self._esperar_conteo_notepad(esperado),
            "nuestro proceso notepad no aparecio en tasklist",
        )
        self.assertTrue(
            self.manager.is_application_open("Notepad"),
            "notepad propio no detectado como abierto",
        )
        self.assertEqual(_contar_procesos(_NOTEPAD), esperado)

        # Terminamos SOLO nuestro proceso; la cuenta debe volver al inicial.
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.proc = None
        self.assertTrue(
            self._esperar_conteo_notepad(self.conteo_notepad_inicial),
            "el proceso notepad propio no se termino",
        )
        self.assertEqual(_contar_procesos(_NOTEPAD), self.conteo_notepad_inicial)
        self.assertEqual(
            self.manager.is_application_open("Notepad"),
            self.conteo_notepad_inicial > 0,
        )

    def test_3_8_5_3_2_app_abierta_no_lanza_proceso_nuevo_si_preflight_rechaza(self):
        # Notepad puede estar ya abierto (proceso del usuario, ajeno; no se toca).
        # Su ejecutable no pasa preflight (no localizable via shutil.which en
        # Windows 11), por lo que open_application debe rechazarlo SIN lanzar
        # un proceso nuevo: el conteo de notepad debe mantenerse estable.
        self.proc = subprocess.Popen([_NOTEPAD])
        self.assertIsNotNone(self.proc.pid)
        esperado = self.conteo_notepad_inicial + 1
        self.assertTrue(
            self._esperar_conteo_notepad(esperado),
            "nuestro proceso notepad no aparecio en tasklist",
        )
        conteo_antes_de_abrir = _contar_procesos(_NOTEPAD)

        with self.assertRaises(RuntimeError):
            open_application("Notepad")

        # Verificacion real: no se lanzo un proceso notepad nuevo.
        self.assertEqual(
            _contar_procesos(_NOTEPAD),
            conteo_antes_de_abrir,
            "open_application lanzo un proceso notepad nuevo a pesar de rechazar el preflight",
        )
