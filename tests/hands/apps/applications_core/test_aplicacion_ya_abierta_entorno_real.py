# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.3.

Comprueba contra el SO real que JARVIS detecta cuando una aplicacion ya
esta abierta y reutiliza la instancia existente en vez de lanzar un proceso
nuevo.

Verificacion a nivel de proceso (tasklist del SO real):
* ``notepad.exe``: el usuario puede tenerlo ya abierto; ese proceso es ajeno
  y nunca se toca. La prueba lanza su propio proceso, detecta el PID real
  de la instancia lanzada (en Windows 11 notepad.exe es un stub que lanza
  un proceso independiente), lo termina y compara antes y despues.
* ``mspaint.exe`` (Paint): camino negativo real, sin tocar ningun proceso.

No se mueve ni cierra ninguna ventana del usuario. Al terminar cada prueba
(tambien si falla) se cierra lo que la prueba creo y nada mas: los procesos
notepad nuevos respecto a la linea base tomada antes de lanzar y, en los
procesos notepad que ya existian (Windows 11 entrega la ventana nueva al
proceso que ya estaba abierto), solo las ventanas nuevas respecto a la
instantanea previa.
"""

import subprocess
import time
import unittest
from unittest.mock import patch

from src.hands.apps.applications_core import ApplicationManager, open_application
from src.hands.inventory.process_tree import (
    cerrar_proceso_por_pid,
    cerrar_procesos_nuevos,
    esperar_pid_nuevo,
    obtener_pids_por_nombre,
)

_NOTEPAD = "notepad.exe"


def _contar_procesos(nombre_ejecutable: str) -> int:
    """Cuenta procesos con ese nombre de imagen en tasklist del SO real."""
    return len(obtener_pids_por_nombre(nombre_ejecutable))


def _escritorio():
    """Contrato de escritorio real del SO, o None si no esta disponible."""
    try:
        from src.desktop.platform_contract import get_desktop_platform

        return get_desktop_platform()
    except Exception:
        return None


def _ids_ventanas(escritorio, pid=None) -> set:
    """Identificadores de las ventanas (de un PID, o todas) en este momento."""
    if escritorio is None:
        return set()
    try:
        if pid is None:
            resultado = escritorio.list_windows(visible_only=False)
        else:
            resultado = escritorio.list_windows(pid=int(pid), visible_only=False)
    except Exception:
        return set()
    if not getattr(resultado, "ok", False):
        return set()
    return {int(v.window_id) for v in (resultado.value or [])}


class TestAplicacionYaAbiertaEntornoReal(unittest.TestCase):
    """3.8.5.3: comprobar si la aplicacion ya esta abierta y reutilizarla."""

    def setUp(self):
        self.manager = ApplicationManager()
        self.conteo_notepad_inicial = _contar_procesos(_NOTEPAD)
        self.pids_notepad_inicial = obtener_pids_por_nombre(_NOTEPAD)
        self.pid_notepad_propio = None
        self.proc = None
        # Linea base de ventanas ANTES de lanzar nada: lo que no este aqui al
        # terminar lo ha creado la prueba.
        self.escritorio = _escritorio()
        self.ventanas_iniciales = _ids_ventanas(self.escritorio)
        self.addCleanup(self._cerrar_lo_creado_por_la_prueba)

    def _cerrar_lo_creado_por_la_prueba(self):
        """Cierra solo lo creado durante la prueba, nunca lo preexistente.

        1. Ventanas nuevas de procesos notepad que ya existian (la ventana que
           Windows 11 abre en el proceso del usuario): cierre ordenado de esa
           ventana concreta, sin matar el proceso ajeno.
        2. Procesos notepad nuevos respecto a la linea base (incluido el real
           que arranca el stub notepad.exe, con otro PID).
        3. El stub lanzado con Popen, si siguiera vivo.
        """
        for pid in sorted(self.pids_notepad_inicial & obtener_pids_por_nombre(_NOTEPAD)):
            for ventana in sorted(_ids_ventanas(self.escritorio, pid) - self.ventanas_iniciales):
                try:
                    self.escritorio.close_window(ventana)
                except Exception:
                    pass
        try:
            cerrar_procesos_nuevos(_NOTEPAD, set(self.pids_notepad_inicial))
        except Exception:
            pass
        if self.pid_notepad_propio is not None:
            try:
                cerrar_proceso_por_pid(self.pid_notepad_propio)
            except Exception:
                pass
            self.pid_notepad_propio = None
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                pass

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

        # Lanzamos nuestro propio proceso Notepad. En Windows 11 notepad.exe
        # es un stub: el PID de Popen no es el del proceso real de la
        # ventana. Detectamos el PID real comparando antes y despues.
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

        # Identificar el PID real del notepad lanzado por esta prueba.
        pid_real = esperar_pid_nuevo(
            _NOTEPAD, self.pids_notepad_inicial, timeout_segundos=10.0
        )
        self.assertIsNotNone(
            pid_real, "no se pudo identificar el PID real del notepad lanzado"
        )
        self.pid_notepad_propio = pid_real

        # Terminamos SOLO nuestro proceso; la cuenta debe volver al inicial.
        self.assertTrue(
            cerrar_proceso_por_pid(pid_real),
            "el proceso notepad propio no se termino tras cerrar por PID",
        )
        self.assertTrue(
            self._esperar_conteo_notepad(self.conteo_notepad_inicial),
            "el conteo de notepad no volvio a la linea base",
        )
        self.assertEqual(_contar_procesos(_NOTEPAD), self.conteo_notepad_inicial)
        self.assertEqual(
            self.manager.is_application_open("Notepad"),
            self.conteo_notepad_inicial > 0,
        )

    def test_3_8_5_3_2_app_abierta_se_reutiliza_sin_lanzar_proceso_nuevo(self):
        # Con nuestro Notepad abierto, open_application("Notepad") debe
        # reutilizar la instancia existente (capacidad OPEN sin precondicion
        # "closed") y NO lanzar un proceso nuevo: el conteo de notepad se
        # mantiene. (Antes Notepad no pasaba el preflight en Windows 11 y la
        # prueba esperaba un rechazo; hoy el preflight y la resolucion local
        # localizan notepad.exe, asi que se comprueba la reutilizacion real.)
        self.proc = subprocess.Popen([_NOTEPAD])
        self.assertIsNotNone(self.proc.pid)
        esperado = self.conteo_notepad_inicial + 1
        self.assertTrue(
            self._esperar_conteo_notepad(esperado),
            "nuestro proceso notepad no aparecio en tasklist",
        )

        # Identificar el PID real del notepad lanzado por esta prueba para
        # poder cerrarlo al terminar sin tocar el del usuario.
        pid_real = esperar_pid_nuevo(
            _NOTEPAD, self.pids_notepad_inicial, timeout_segundos=10.0
        )
        self.assertIsNotNone(
            pid_real, "no se pudo identificar el PID real del notepad lanzado"
        )
        self.pid_notepad_propio = pid_real
        pids_antes_de_abrir = obtener_pids_por_nombre(_NOTEPAD)

        resultado = open_application("Notepad")

        self.assertIn("ya esta abierta", resultado)
        self.assertIn("reutilizo", resultado)
        # Verificacion real: no se lanzo un proceso notepad nuevo.
        self.assertEqual(
            obtener_pids_por_nombre(_NOTEPAD),
            pids_antes_de_abrir,
            "open_application lanzo un proceso notepad nuevo en vez de reutilizar el abierto",
        )
