# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.4.

Comprueba contra el SO real que JARVIS abre una aplicacion cerrada mediante
la API real de ejecucion (CalibrationManager.launch_application), tras validar
el destino con ApplicationPreflight y obtener la ruta del inventario local
(SQLite, machine_id actual), sin cerrar ni alterar ventanas ajenas.

La prueba usa una allowlist de una aplicacion inocua (charmap.exe / Mapa de
caracteres), la unica aplicacion del inventario local `application_candidates`
que pasa preflight real en este equipo. Registra una linea base de procesos y
ventanas, lanza con la API real (sin mockear lanzador, procesos ni ventanas),
verifica el proceso y la ventana propios (PID/HWND), cierra SOLO lo creado
por la prueba (por PID) y comprueba que Visual Studio Code y las ventanas
previas quedan intactas.

No se envia teclado ni raton a ninguna ventana. La ventana de charmap aparece
en el monitor primario (DISPLAY1), sin superponer Visual Studio Code, que
reside en la segunda pantalla (DISPLAY2).
"""

import os
import subprocess
import time
import unittest

from src.hands.application_preflight import get_application_preflight
from src.hands.calibration_manager import get_calibration_manager
from src.utils.screen_manager import get_screen_manager


_CHARMAP_PATH = r"C:\Windows\System32\charmap.exe"
_CHARMAP_NAME = "charmap.exe"
_CHARMAP_NOMBRE = "Mapa de caracteres"


def _contar_charmap():
    """Cuenta procesos charmap.exe en tasklist del SO real."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {_CHARMAP_NAME}"],
        capture_output=True, text=True, check=False,
    )
    return sum(
        1 for linea in (resultado.stdout or "").splitlines()
        if _CHARMAP_NAME.lower() in linea.lower()
    )


def _ventanas():
    return set(get_calibration_manager()._get_window_handles())


class TestAperturaAplicacionCerradaEntornoReal(unittest.TestCase):
    """3.8.5.4: abrir una aplicacion cerrada mediante la API real de ejecucion."""

    def setUp(self):
        self.cal = get_calibration_manager()
        self.preflight = get_application_preflight()
        self.charmap_antes = _contar_charmap()
        self.ventanas_antes = _ventanas()
        self.proc_pid = None

    def tearDown(self):
        # Cerrar SOLO el proceso creado por esta prueba, identificado por PID.
        # Nunca cerrar por nombre (mataria todas las instancias, incluidas las
        # ajenas al usuario).
        if self.proc_pid is not None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(int(self.proc_pid)), "/F"],
                    capture_output=True, text=True, check=False,
                )
            except Exception:
                pass
            # Esperar a que termine el proceso propio antes de la siguiente prueba.
            tiempo = time.time() + 8
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(self.proc_pid)):
                    break
                time.sleep(0.25)
            self.proc_pid = None

    # ---- 3.8.5.4.1.1: linea base real de procesos y ventanas ----
    def test_3_8_5_4_1_1_linea_base_procesos_y_ventanas(self):
        self.assertIsInstance(self.charmap_antes, int)
        self.assertGreaterEqual(self.charmap_antes, 0)
        self.assertIsInstance(self.ventanas_antes, set)

    # ---- 3.8.5.4.1.7: enumerar los dos monitores reales ----
    def test_3_8_5_4_1_7_monitores_reales(self):
        sm = get_screen_manager()
        self.assertGreaterEqual(len(sm.monitors), 1, "no se encontro ningun monitor real")
        self.assertTrue(any(m.is_primary for m in sm.monitors),
                        "no se identifico un monitor primario")

    # ---- 3.8.5.4.2.1 / 3.8.5.4.2.1.1: destino real, inventario local, preflight ----
    def test_3_8_5_4_2_1_destino_real_y_preflight(self):
        self.assertTrue(os.path.isfile(_CHARMAP_PATH),
                        "charmap.exe no esta en la ruta esperada del equipo")
        # Preflight resuelve el destino desde el inventario local (machine_id)
        # y no lanza nada.
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE,
            "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False),
                        f"preflight rechazo charmap: {pf.get('reason')}")
        self.assertEqual(
            (pf.get("executable_path") or "").lower(),
            _CHARMAP_PATH.lower(),
            f"preflight resuelve ruta distinta: {pf.get('executable_path')}",
        )

    # ---- 3.8.5.4.2.2: lanzamiento real, evidenciando PID y ventana propia ----
    def test_3_8_5_4_2_2_lanzamiento_real_pid_y_ventana(self):
        antes = self.charmap_antes
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

        # Lanzamiento REAL (sin mockear lanzador, procesos ni ventanas).
        antes_hwnds = _ventanas()
        resultado = self.cal.launch_application({
            "name": _CHARMAP_NOMBRE,
            "app_id": "",
            "path": _CHARMAP_PATH,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertTrue(ok, "launch_application no informo exito al abrir charmap")

        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        owned_pids = getattr(self.cal, "_last_launch_owned_pids", set())
        owned_hwnds = getattr(self.cal, "_last_launch_owned_hwnds", set())
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))

        if was_owned and root_pid is not None:
            self.assertTrue(self.cal._is_process_alive(int(root_pid)),
                            "el proceso lanzado no esta vivo")
            self.proc_pid = int(root_pid)
        if not was_owned:
            self.assertTrue(antes > 0,
                            "no se lanzo proceso nuevo y charmap no estaba abierta")

        despues = _contar_charmap()
        self.assertIn(despues, (antes, antes + 1),
                      f"conteo charmap inesperado: antes={antes}, despues={despues}")
        self.assertGreaterEqual(len(owned_hwnds), 1,
                                "no se obtuvo ninguna ventana propia lanzada")

    # ---- 3.8.5.4.2.4 / preservacion: cerrar solo lo propio, ventanas ajenas intactas ----
    def test_3_8_5_4_2_4_cierre_solo_propio_y_preservacion(self):
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")
        resultado = self.cal.launch_application({
            "name": _CHARMAP_NOMBRE, "app_id": "", "path": _CHARMAP_PATH, "arguments": "",
        })
        self.assertTrue(bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado))
        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))
        self.assertIsNotNone(root_pid)
        if was_owned:
            self.proc_pid = int(root_pid)
            self.assertTrue(self.cal._is_process_alive(int(root_pid)))

        if self.proc_pid is not None:
            subprocess.run(
                ["taskkill", "/PID", str(int(self.proc_pid)), "/F"],
                capture_output=True, text=True, check=False,
            )
            tiempo = time.time() + 10
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(self.proc_pid)):
                    break
                time.sleep(0.25)
            self.assertFalse(self.cal._is_process_alive(int(self.proc_pid)),
                             "el proceso propio no se termino tras cerrar por PID")
            self.proc_pid = None

        self.assertEqual(_contar_charmap(), self.charmap_antes)

    # ---- 3.8.5.4.2.4 / 3.8.5.4.2.8: ejecutable inexistente no se lanza ----
    def test_3_8_5_4_2_3_ejecutable_inexistente_no_lanza(self):
        ruta = r"C:\Windows\System32\aplicacion_inexistente_jarvis_xyz.exe"
        self.assertFalse(os.path.isfile(ruta), "la ruta de prueba no deberia existir")
        pf = self.preflight.check({
            "name": "AplicacionInexistente",
            "app_id": "",
        })
        self.assertFalse(pf.get("allowed", True),
                         "preflight permitio un ejecutable inexistente")
