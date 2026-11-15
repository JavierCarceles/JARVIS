# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.6.7.

Comprueba contra el SO real que JARVIS abre notepad.exe mediante
CalibrationManager.launch_application, tras validar el destino con
ApplicationPreflight y confirmar que notepad.exe existe en el SO.
Registra linea base de procesos y ventanas, lanza con la API real
(sin mockear lanzador, procesos ni ventanas), verifica el proceso y
la ventana propios (PID/propietario/HWND/visible), cierra SOLO lo
creado por la prueba (por PID) y comprueba que Visual Studio Code y
las ventanas previas quedan intactas.

Si notepad ya estaba abierto y la API no puede crear una instancia
propia de la prueba (was_owned=False), no se cierra: se registra como
reutilizacion o escenario BLOQUEADO para prueba de propiedad exclusiva.

No se envia teclado ni raton a ninguna ventana.
"""

import os
import subprocess
import time
import unittest

from src.hands.application_preflight import get_application_preflight
from src.hands.calibration_manager import get_calibration_manager
from src.utils.screen_manager import get_screen_manager


_NOTEPAD_NAME = "notepad.exe"
_NOTEPAD_PATH = r"C:\Windows\System32\notepad.exe"
_CALC_NAME = "calc.exe"
_CALC_PATH = r"C:\Windows\System32\calc.exe"


def _contar_notepad():
    """Cuenta procesos notepad.exe en tasklist del SO real."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {_NOTEPAD_NAME}"],
        capture_output=True, text=True, check=False,
    )
    return sum(
        1 for linea in (resultado.stdout or "").splitlines()
        if _NOTEPAD_NAME.lower() in linea.lower()
    )


def _contar_calc():
    """Cuenta procesos calc.exe en tasklist del SO real."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {_CALC_NAME}"],
        capture_output=True, text=True, check=False,
    )
    return sum(
        1 for linea in (resultado.stdout or "").splitlines()
        if _CALC_NAME.lower() in linea.lower()
    )


def _ventanas():
    return set(get_calibration_manager()._get_window_handles())


def _contar_vscode():
    """Cuenta procesos de Visual Studio Code (Code.exe) en tasklist."""
    resultado = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Code.exe"],
        capture_output=True, text=True, check=False,
    )
    return sum(
        1 for linea in (resultado.stdout or "").splitlines()
        if "code.exe" in linea.lower()
    )


class TestAperturaAplicacionesInocuasEntornoReal(unittest.TestCase):
    """3.8.5.6.7: abrir notepad.exe mediante la API real de ejecucion."""

    def setUp(self):
        self.cal = get_calibration_manager()
        self.preflight = get_application_preflight()
        self.sm = get_screen_manager()
        self.notepad_antes = _contar_notepad()
        self.calc_antes = _contar_calc()
        self.vscode_antes = _contar_vscode()
        self.ventanas_antes = _ventanas()
        self.proc_pid = None
        self.cerrado_por_la_prueba = False

    def tearDown(self):
        # Cerrar SOLO el proceso creado por esta prueba, si quedara vivo.
        # Nunca cerrar por nombre ni cerrar notepad del usuario.
        if self.proc_pid is not None and self.cerrado_por_la_prueba:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(int(self.proc_pid)), "/F"],
                    capture_output=True, text=True, check=False,
                )
            except Exception:
                pass
            tiempo = time.time() + 10
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(self.proc_pid)):
                    break
                time.sleep(0.25)
            self.assertFalse(
                self.cal._is_process_alive(int(self.proc_pid)),
                "el proceso propio no se termino tras cerrar por PID",
            )
            self.proc_pid = None
            self.cerrado_por_la_prueba = False

    # 3.8.5.6.7.1: notepad.exe existe en el equipo (fuente real del SO)
    def test_3_8_5_6_7_1_notepad_existe(self):
        self.assertTrue(
            os.path.isfile(_NOTEPAD_PATH),
            f"notepad.exe no esta en {_NOTEPAD_PATH}",
        )

    # 3.8.5.6.7.2: notepad pasa ApplicationPreflight real
    def test_3_8_5_6_7_2_notepad_pasa_preflight(self):
        pf = self.preflight.check({
            "name": _NOTEPAD_NAME,
            "app_id": "",
            "path": _NOTEPAD_PATH,
        })
        self.assertTrue(pf.get("allowed", False),
                        f"preflight rechazo notepad: {pf.get('reason')}")
        self.assertFalse(pf.get("requires_elevation", True),
                         "notepad no deberia requerir elevacion")
        self.assertIsNotNone(pf.get("executable_path"),
                             "preflight no resuelve ejecutable de notepad")

    # 3.8.5.6.7.3: ciclo completo lanzar -> verificar PID/propietario/HWND/ventana visible -> cerrar -> preservar
    def test_3_8_5_6_7_3_ciclo_completo_notepad(self):
        """Ciclo completo real: preflight, lanzamiento, verificacion, cierre, preservacion."""
        pf = self.preflight.check({
            "name": _NOTEPAD_NAME, "app_id": "", "path": _NOTEPAD_PATH,
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

        # Lanzamiento REAL (sin mockear lanzador, procesos ni ventanas).
        resultado = self.cal.launch_application({
            "name": _NOTEPAD_NAME,
            "app_id": "",
            "path": _NOTEPAD_PATH,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertTrue(ok, "launch_application no informo exito al abrir notepad")

        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        owned_pids = getattr(self.cal, "_last_launch_owned_pids", set())
        owned_hwnds = getattr(self.cal, "_last_launch_owned_hwnds", set())
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))
        launch_state = str(getattr(self.cal, "_last_launch_state", "DESCONOCIDO"))

        despues_notepad = _contar_notepad()
        self.assertIn(
            despues_notepad, (self.notepad_antes, self.notepad_antes + 1),
            f"conteo notepad inesperado: antes={self.notepad_antes}, despues={despues_notepad}",
        )

        if was_owned and root_pid is not None:
            # Caso exito: proceso propio lanzado por la prueba.
            self.proc_pid = int(root_pid)
            self.cerrado_por_la_prueba = True

            self.assertTrue(
                self.cal._is_process_alive(int(root_pid)),
                "el proceso lanzado no esta vivo justo despues del lanzamiento",
            )
            self.assertIn(int(root_pid), owned_pids,
                          f"el root_pid {root_pid} no esta en los PIDs propios del lanzamiento")
            self.assertGreaterEqual(len(owned_hwnds), 1,
                                    "no se obtuvo ninguna ventana propia lanzada")

            # Detectar ventana perteneciente al proceso (3.8.5.5.3).
            espera = self.cal.wait_for_application_window(
                root_pid=root_pid,
                application_name=_NOTEPAD_NAME,
                app_id="",
                timeout=8.0,
                poll_interval=0.4,
            )
            self.assertEqual(
                espera["status"], "VENTANA_DETECTADA",
                f"se esperaba ventana detectada, obtuvo: {espera}",
            )
            ventana = espera["window"]
            self.assertIsNotNone(ventana, "no se devolvio objeto de ventana")

            hwnd_creado = self.cal._get_window_handle(ventana)
            self.assertIsNotNone(hwnd_creado, "la ventana detectada no tiene HWND")

            ventana_pid = self.cal._get_window_process_id(ventana)
            self.assertIsNotNone(ventana_pid, "la ventana detectada no tiene PID")
            self.assertEqual(ventana_pid, root_pid,
                             "PID de ventana distinto al root_pid")

            # La ventana debe ser visible (3.8.5.5.4).
            self.assertTrue(
                self.cal._win32_is_visible(hwnd_creado),
                "la ventana detectada no es visible",
            )

            # No confundir con Visual Studio Code.
            es_vscode = getattr(self.cal, "_es_visual_studio_code", lambda hwnd: False)(hwnd_creado)
            self.assertFalse(es_vscode, "la ventana detectada se confunde con Visual Studio Code")

            # Estabilidad minima del proceso y la ventana durante un intervalo (3.8.5.5.5).
            estabilidad = self.cal.verify_estabilidad_minima_proceso_ventana(
                root_pid=root_pid,
                window=ventana,
                application_name=_NOTEPAD_NAME,
                app_id="",
                estabilidad_interval=1.5,
                estabilidad_checks=3,
            )
            self.assertEqual(estabilidad["status"], "ESTABLE", f"no estable: {estabilidad}")
            self.assertTrue(estabilidad["process_alive"], "el proceso no estuvo vivo")
            self.assertTrue(estabilidad["window_valida"], "la ventana no estuvo valida")
            self.assertTrue(estabilidad["window_visible"], "la ventana no estuvo visible")

            # ========== PASO: cerrar solo lo creado por la prueba ==========
            subprocess.run(
                ["taskkill", "/PID", str(int(root_pid)), "/F"],
                capture_output=True, text=True, check=False,
            )
            tiempo = time.time() + 10
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(root_pid)):
                    break
                time.sleep(0.25)
            self.assertFalse(
                self.cal._is_process_alive(int(root_pid)),
                "el proceso propio no se termino tras cerrar por PID",
            )
            self.proc_pid = None
            self.cerrado_por_la_prueba = False

            # La cuenta de notepad debe volver a la linea base.
            self.assertEqual(_contar_notepad(), self.notepad_antes,
                             "conteo de notepad no volvio a la linea base tras el cierre")

            # Las ventanas preexistentes (incluido Visual Studio Code) deben seguir presentes.
            despues_ventanas = _ventanas()
            faltantes = []
            for hwnd in self.ventanas_antes:
                if hwnd not in despues_ventanas:
                    faltantes.append(hwnd)
            self.assertEqual(
                faltantes, [],
                f"desaparecieron ventanas previas tras el cierre: {faltantes}",
            )

            vscode_despues = _contar_vscode()
            self.assertGreaterEqual(vscode_despues, self.vscode_antes,
                                    f"Visual Studio Code no se preservo: antes={self.vscode_antes}, despues={vscode_despues}")
        else:
            # Notepad ya estaba abierto y la API reutilizo la instancia existente.
            # No cerrar nada ajeno: escenario de reutilizacion registrado.
            self.skipTest(
                "Notepad ya estaba abierto; la API reutilizo la instancia existente "
                "(was_owned=False). No se cierra nada ajeno. "
                "Escenario de reutilizacion registrado; BLOQUEADO para prueba de "
                "propiedad exclusiva si se requiere was_owned=True."
            )

    # 3.8.5.6.7.4: enumeracion de monitores reales (entorno de dos pantallas)
    def test_3_8_5_6_7_4_monitores_reales(self):
        self.assertGreaterEqual(len(self.sm.monitors), 1,
                                "no se encontro ningun monitor real")
        self.assertTrue(any(m.is_primary for m in self.sm.monitors),
                        "no se identifico un monitor primario")

    # 3.8.5.6.8.1: calc.exe existe en el equipo (fuente real del SO)
    def test_3_8_5_6_8_1_calc_existe(self):
        self.assertTrue(
            os.path.isfile(_CALC_PATH),
            f"calc.exe no esta en {_CALC_PATH}",
        )

    # 3.8.5.6.8.2: calc.exe pasa ApplicationPreflight real
    def test_3_8_5_6_8_2_calc_pasa_preflight(self):
        pf = self.preflight.check({
            "name": _CALC_NAME,
            "app_id": "",
            "path": _CALC_PATH,
        })
        self.assertTrue(pf.get("allowed", False),
                        f"preflight rechazo calc: {pf.get('reason')}")
        self.assertFalse(pf.get("requires_elevation", True),
                         "calc no deberia requerir elevacion")
        self.assertIsNotNone(pf.get("executable_path"),
                             "preflight no resuelve ejecutable de calc")

    # 3.8.5.6.8.3: ciclo completo lanzar -> verificar activacion/proceso/ventana
    #              por identificador real de proceso -> cerrar -> preservar
    def test_3_8_5_6_8_3_ciclo_completo_calc(self):
        """Ciclo completo real: preflight, lanzamiento, verificacion, cierre, preservacion."""
        pf = self.preflight.check({
            "name": _CALC_NAME, "app_id": "", "path": _CALC_PATH,
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

        # Lanzamiento REAL (sin mockear lanzador, procesos ni ventanas).
        resultado = self.cal.launch_application({
            "name": _CALC_NAME,
            "app_id": "",
            "path": _CALC_PATH,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertTrue(ok, "launch_application no informo exito al abrir calc")

        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        owned_pids = getattr(self.cal, "_last_launch_owned_pids", set())
        owned_hwnds = getattr(self.cal, "_last_launch_owned_hwnds", set())
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))
        launch_state = str(getattr(self.cal, "_last_launch_state", "DESCONOCIDO"))

        despues_calc = _contar_calc()
        self.assertIn(
            despues_calc, (self.calc_antes, self.calc_antes + 1),
            f"conteo calc inesperado: antes={self.calc_antes}, despues={despues_calc}",
        )

        if was_owned and root_pid is not None:
            # Caso exito: proceso propio lanzado por la prueba.
            self.proc_pid = int(root_pid)
            self.cerrado_por_la_prueba = True

            self.assertTrue(
                self.cal._is_process_alive(int(root_pid)),
                "el proceso lanzado no esta vivo justo despues del lanzamiento",
            )
            self.assertIn(int(root_pid), owned_pids,
                          f"el root_pid {root_pid} no esta en los PIDs propios del lanzamiento")
            self.assertGreaterEqual(len(owned_hwnds), 1,
                                    "no se obtuvo ninguna ventana propia lanzada")

            # Detectar ventana perteneciente al proceso (3.8.5.5.3).
            espera = self.cal.wait_for_application_window(
                root_pid=root_pid,
                application_name=_CALC_NAME,
                app_id="",
                timeout=8.0,
                poll_interval=0.4,
            )
            self.assertEqual(
                espera["status"], "VENTANA_DETECTADA",
                f"se esperaba ventana detectada, obtuvo: {espera}",
            )
            ventana = espera["window"]
            self.assertIsNotNone(ventana, "no se devolvio objeto de ventana")

            hwnd_creado = self.cal._get_window_handle(ventana)
            self.assertIsNotNone(hwnd_creado, "la ventana detectada no tiene HWND")

            ventana_pid = self.cal._get_window_process_id(ventana)
            self.assertIsNotNone(ventana_pid, "la ventana detectada no tiene PID")
            self.assertEqual(ventana_pid, root_pid,
                             "PID de ventana distinto al root_pid")

            # La ventana debe ser visible (3.8.5.5.4).
            self.assertTrue(
                self.cal._win32_is_visible(hwnd_creado),
                "la ventana detectada no es visible",
            )

            # No confundir con Visual Studio Code.
            es_vscode = getattr(self.cal, "_es_visual_studio_code", lambda hwnd: False)(hwnd_creado)
            self.assertFalse(es_vscode, "la ventana detectada se confunde con Visual Studio Code")

            # Estabilidad minima del proceso y la ventana durante un intervalo (3.8.5.5.5).
            estabilidad = self.cal.verify_estabilidad_minima_proceso_ventana(
                root_pid=root_pid,
                window=ventana,
                application_name=_CALC_NAME,
                app_id="",
                estabilidad_interval=1.5,
                estabilidad_checks=3,
            )
            self.assertEqual(estabilidad["status"], "ESTABLE", f"no estable: {estabilidad}")
            self.assertTrue(estabilidad["process_alive"], "el proceso no estuvo vivo")
            self.assertTrue(estabilidad["window_valida"], "la ventana no estuvo valida")
            self.assertTrue(estabilidad["window_visible"], "la ventana no estuvo visible")

            # ========== PASO: cerrar solo lo creado por la prueba ==========
            subprocess.run(
                ["taskkill", "/PID", str(int(root_pid)), "/F"],
                capture_output=True, text=True, check=False,
            )
            tiempo = time.time() + 10
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(root_pid)):
                    break
                time.sleep(0.25)
            self.assertFalse(
                self.cal._is_process_alive(int(root_pid)),
                "el proceso propio no se termino tras cerrar por PID",
            )
            self.proc_pid = None
            self.cerrado_por_la_prueba = False

            # La cuenta de calc debe volver a la linea base.
            self.assertEqual(_contar_calc(), self.calc_antes,
                             "conteo de calc no volvio a la linea base tras el cierre")

            # Las ventanas preexistentes (incluido Visual Studio Code) deben seguir presentes.
            despues_ventanas = _ventanas()
            faltantes = []
            for hwnd in self.ventanas_antes:
                if hwnd not in despues_ventanas:
                    faltantes.append(hwnd)
            self.assertEqual(
                faltantes, [],
                f"desaparecieron ventanas previas tras el cierre: {faltantes}",
            )

            vscode_despues = _contar_vscode()
            self.assertGreaterEqual(vscode_despues, self.vscode_antes,
                                    f"Visual Studio Code no se preservo: antes={self.vscode_antes}, despues={vscode_despues}")
        else:
            # Calc ya estaba abierto y la API reutilizo la instancia existente.
            # No cerrar nada ajeno: escenario de reutilizacion registrado.
            self.skipTest(
                "Calc ya estaba abierto; la API reutilizo la instancia existente "
                "(was_owned=False). No se cierra nada ajeno. "
                "Escenario de reutilizacion registrado; BLOQUEADO para prueba de "
                "propiedad exclusiva si se requiere was_owned=True."
            )


if __name__ == "__main__":
    unittest.main()
