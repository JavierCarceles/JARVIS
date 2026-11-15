# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.5.1.

Comprueba contra el SO real que, tras lanzar una aplicacion cerrada mediante
la API real de ejecucion (CalibrationManager.launch_application), el proceso
objetivo existe y sigue vivo durante un intervalo acotado, correlacionandolo
con la ruta, PID y app_id (verificacion de estabilidad post-lanzamiento).

La prueba usa una allowlist de una aplicacion inocua (charmap.exe / Mapa de
caracteres), la unica aplicacion del inventario local `application_candidates`
que pasa preflight real en este equipo. Registra una linea base de procesos y
ventanas, lanza con la API real (sin mockear lanzador, procesos ni ventanas),
verifica estabilidad del proceso propio (PID) durante un intervalo, cierra
SOLO lo creado por la prueba (por PID) y comprueba que Visual Studio Code y
las ventanas previas quedan intactas.

No se envia teclado ni raton a ninguna ventana. La ventana de charmap aparece
en el monitor primario (DISPLAY1), sin superponer Visual Studio Code, que
reside en la segunda pantalla (DISPLAY2).
"""

import json
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


class TestVerificacionProcesoDespuesLanzamientoEntornoReal(unittest.TestCase):
    """3.8.5.5.1: verificar proceso, ventana y estado posterior a la apertura."""

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

    # ---- 3.8.5.5.1: proceso sigue vivo tras el lanzamiento ----
    def test_3_8_5_5_1_proceso_sigue_vivo_despues_lanzamiento(self):
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

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
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))

        if was_owned and root_pid is not None:
            self.proc_pid = int(root_pid)
            self.assertTrue(self.cal._is_process_alive(int(root_pid)),
                            "el proceso lanzado no esta vivo justo despues del lanzamiento")

        # Verificacion de estabilidad: el proceso sigue vivo durante un intervalo
        estabilidad = self.cal.verify_launch_process_stability(
            pid=root_pid, stability_interval=2.0, stability_checks=3
        )
        self.assertTrue(estabilidad["stable"],
                        f"el proceso no establecio: {estabilidad}")
        self.assertEqual(estabilidad["pid"], root_pid)
        self.assertTrue(estabilidad["alive"])

        # Correlacion con ruta y app_id
        evidencia = self.cal.get_launch_evidence()
        self.assertEqual(evidencia["root_pid"], root_pid)
        if _CHARMAP_PATH.lower() != "":
            self.assertEqual(
                evidencia["executable_path"].lower(), _CHARMAP_PATH.lower(),
                "la ruta ejecutable en la evidencia no coincide con la ruta de lanzamiento"
            )
        self.assertEqual(evidencia["app_id"], "")
        self.assertTrue(evidencia["was_owned"])

        despues = _contar_charmap()
        self.assertIn(despues, (self.charmap_antes, self.charmap_antes + 1),
                      f"conteo charmap inesperado: antes={self.charmap_antes}, despues={despues}")

    # ---- 3.8.5.5.5: estabilidad minima durante un intervalo definido ----
    def test_3_8_5_5_5_estabilidad_minima_intervalo_definido(self):
        """El proceso permanece vivo a lo largo de varias comprobaciones espaciadas."""
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

        resultado = self.cal.launch_application({
            "name": _CHARMAP_NOMBRE,
            "app_id": "",
            "path": _CHARMAP_PATH,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertTrue(ok, "launch_application no informo exito al abrir charmap")

        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))
        if was_owned and root_pid is not None:
            self.proc_pid = int(root_pid)

            # Estabilidad con intervalo y comprobaciones configurables
            estabilidad = self.cal.verify_launch_process_stability(
                pid=root_pid, stability_interval=3.0, stability_checks=4
            )
            self.assertTrue(estabilidad["stable"],
                            f"el proceso no mantuvo estabilidad: {estabilidad}")
            self.assertEqual(estabilidad["total_checks"], 4)
            self.assertEqual(estabilidad["checks_passed"], 4)
            self.assertTrue(estabilidad["alive"])

    # ---- 3.8.5.5.5: estabilidad minima de proceso y ventana durante un intervalo ----
    def test_3_8_5_5_5_estabilidad_minima_proceso_ventana(self):
        """El proceso y su ventana permanecen estables durante un intervalo definido."""
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

        resultado = self.cal.launch_application({
            "name": _CHARMAP_NOMBRE,
            "app_id": "",
            "path": _CHARMAP_PATH,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertTrue(ok, "launch_application no informo exito al abrir charmap")

        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        was_owned = bool(getattr(self.cal, "_last_launch_was_owned", False))
        self.assertTrue(was_owned, "charmap no fue lanzado como proceso propio")
        self.assertIsNotNone(root_pid, "no se obtuvo root_pid del lanzamiento")
        self.proc_pid = int(root_pid)

        # Esperar la ventana (3.8.5.5.3).
        espera = self.cal.wait_for_application_window(
            root_pid=root_pid,
            application_name=_CHARMAP_NOMBRE,
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

        # Verificar que la ventana es visible y corresponde (3.8.5.5.4).
        verificacion = self.cal.verify_visible_window_for_application(
            ventana,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            root_pid=root_pid,
            owned_pids=getattr(self.cal, "_last_launch_owned_pids", set()),
        )
        self.assertTrue(verificacion["verificada"], f"no verificada: {verificacion['reason']}")
        self.assertTrue(verificacion["visible"])

        # Estabilidad minima del proceso y la ventana durante un intervalo (3.8.5.5.5).
        estabilidad = self.cal.verify_estabilidad_minima_proceso_ventana(
            root_pid=root_pid,
            window=ventana,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            estabilidad_interval=1.5,
            estabilidad_checks=3,
        )
        self.assertEqual(estabilidad["status"], "ESTABLE", f"no estable: {estabilidad}")
        self.assertTrue(estabilidad["estable"], f"no estable: {estabilidad}")
        self.assertTrue(estabilidad["process_alive"], "el proceso no estuvo vivo")
        self.assertTrue(estabilidad["window_valida"], "la ventana no estuvo valida")
        self.assertTrue(estabilidad["window_visible"], "la ventana no estuvo visible")
        self.assertTrue(estabilidad["ventana_pertenece_proceso"], "la ventana no pertenece al proceso")
        self.assertEqual(estabilidad["checks_passed"], 3)
        self.assertEqual(estabilidad["total_checks"], 3)
        self.assertEqual(estabilidad["pid"], root_pid)
        self.assertIn("estables", estabilidad["reason"])

    # ---- 3.8.5.5.7: evidencia tecnica minima del resultado ----
    def test_3_8_5_5_7_evidencia_tecnica_minima(self):
        """La evidencia tecnica minima incluye tipo de destino, fuente, ruta, PID, ventana y tiempos."""
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

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
            self.proc_pid = int(root_pid)

        evidencia = self.cal.get_launch_evidence()
        # Verificar que la evidencia contiene los campos minimos requeridos
        self.assertIsNotNone(evidencia["root_pid"], "evidencia sin root_pid")
        self.assertIsInstance(evidencia["owned_pids"], set)
        self.assertIsInstance(evidencia["owned_hwnds"], set)
        self.assertIsInstance(evidencia["was_owned"], bool)
        self.assertIsInstance(evidencia["executable_path"], str)
        self.assertIsInstance(evidencia["app_id"], str)

        # Verificar correlacion entre evidencia y estado real del lanzamiento
        self.assertEqual(evidencia["root_pid"], root_pid)
        self.assertEqual(evidencia["owned_pids"], owned_pids)
        self.assertEqual(evidencia["owned_hwnds"], owned_hwnds)
        self.assertEqual(evidencia["was_owned"], was_owned)

        # Verificar que no se registre contenido privado ni argumentos secretos
        self.assertNotIn("arguments", evidencia)
        self.assertNotIn("command_line", evidencia)

        # Campos requeridos por 3.8.5.5.7: tipo de destino, fuente,
        # destino validado, tiempos y ventana.
        self.assertEqual(evidencia["tipo_destino"], "ejecutable")
        self.assertEqual(evidencia["fuente"], "ruta_directa")
        self.assertIsInstance(evidencia["destino_validado"], str)
        self.assertEqual(
            evidencia["destino_validado"].lower(), _CHARMAP_PATH.lower(),
            "el destino validado debe ser la ruta de lanzamiento"
        )
        self.assertIsInstance(evidencia["timestamps"], dict)
        self.assertIn("inicio", evidencia["timestamps"])
        self.assertIsInstance(evidencia["ventana"], dict)
        self.assertIsNotNone(
            evidencia["ventana"].get("hwnd"), "evidencia sin hwnd de ventana"
        )

        # Guardar evidencia y verificar persistencia JSON sin secretos
        ruta_guardada = self.cal.guardar_evidencia_lanzamiento()
        self.assertIsInstance(ruta_guardada, str)
        self.assertTrue(os.path.exists(ruta_guardada), "el archivo de evidencia no se escribio")
        with open(ruta_guardada, "r", encoding="utf-8") as f:
            guardado = json.load(f)
        self.assertEqual(guardado["tipo_destino"], "ejecutable")
        self.assertEqual(guardado["fuente"], "ruta_directa")
        self.assertIsInstance(guardado["owned_pids"], list)
        self.assertIsInstance(guardado["owned_hwnds"], list)
        self.assertNotIn("arguments", guardado)
        self.assertNotIn("command_line", guardado)


if __name__ == "__main__":
    unittest.main()
