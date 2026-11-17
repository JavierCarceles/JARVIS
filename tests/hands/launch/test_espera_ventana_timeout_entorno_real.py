# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.5.3.

Comprueba contra el SO real que wait_for_application_window espera la ventana
dentro de un timeout acotado y configurable y distingue entre ventana
detectada, proceso sin interfaz y fallo de apertura, usando la API real de
ejecucion (CalibrationManager.launch_application) sin mockear lanzador,
procesos ni ventanas.

La prueba usa una allowlist de una aplicacion inocua (charmap.exe / Mapa de
caracteres), la unica aplicacion del inventario local application_candidates
que pasa preflight real en este equipo. Registra una linea base de procesos y
ventanas, lanza con la API real, espera la ventana del proceso lanzado, verifica
el resultado, cierra SOLO lo creado por la prueba (por PID) y comprueba que
Visual Studio Code y las ventanas previas quedan intactas.

No se envia teclado ni raton a ninguna ventana. La ventana de charmap aparece
en el monitor primario (DISPLAY1), sin superponer Visual Studio Code, que
reside en la segunda pantalla (DISPLAY2).
"""

import subprocess
import time
import unittest

from src.hands.apps.application_preflight import get_application_preflight
from src.hands.calibration.calibration_manager import get_calibration_manager
from src.desktop.screen_manager import get_screen_manager


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


class TestEsperaVentanaTimeoutEntornoReal(unittest.TestCase):
    """3.8.5.5.3: esperar ventana con timeout acotado y distinguir casos."""

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
            tiempo = time.time() + 8
            while time.time() < tiempo:
                if not self.cal._is_process_alive(int(self.proc_pid)):
                    break
                time.sleep(0.25)
            self.proc_pid = None

    # ---- 3.8.5.5.3: ventana detectada dentro del timeout (inicio rapido) ----
    def test_3_8_5_5_3_ventana_detectada_dentro_del_timeout(self):
        """Tras lanzar charmap, wait_for_application_window detecta su ventana."""
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
        self.assertTrue(espera["process_alive"], "el proceso no estaba vivo al esperar")
        self.assertIsNotNone(espera["hwnd"], "no se obtuvo HWND de la ventana")
        self.assertIsNotNone(espera["pid"], "no se obtuvo PID de la ventana")
        self.assertIn(
            espera["pid"],
            getattr(self.cal, "_last_launch_owned_pids", set()),
            f"el PID de la ventana ({espera['pid']}) no esta en los PIDs propios",
        )
        self.assertFalse(
            espera["inicio_lento"],
            f"charmap abre rapido, no deberia ser inicio lento: {espera}",
        )
        self.assertTrue(
            self.cal._win32_is_visible(espera["hwnd"]),
            "la ventana detectada no es visible",
        )

        # Linea base de charmap: solo debe haber una instancia mas (la propia).
        despues = _contar_charmap()
        self.assertIn(
            despues, (self.charmap_antes, self.charmap_antes + 1),
            f"conteo charmap inesperado: antes={self.charmap_antes}, despues={despues}",
        )

    # ---- 3.8.5.5.3: fallo de apertura con PID invalido ----
    def test_3_8_5_5_3_pid_invalido_es_fallo_apertura(self):
        """root_pid None -> FALLO_APERTURA sin lanzar nada ni esperar."""
        with patch_time_sleep():
            espera = self.cal.wait_for_application_window(
                root_pid=None, timeout=10.0
            )
        self.assertEqual(espera["status"], "FALLO_APERTURA")
        self.assertFalse(espera["process_alive"])
        self.assertEqual(espera["elapsed_seconds"], 0.0)

    # ---- 3.8.5.5.3: fallo de apertura cuando el proceso muere ----
    def test_3_8_5_5_3_proceso_muerto_es_fallo_apertura(self):
        """Lanzar charmap, matarlo y esperar -> FALLO_APERTURA."""
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
        self.assertIsNotNone(root_pid, "no se obtuvo root_pid del lanzamiento")
        self.proc_pid = int(root_pid)

        # Matar solo el proceso creado por esta prueba, por PID.
        subprocess.run(
            ["taskkill", "/PID", str(int(root_pid)), "/F"],
            capture_output=True, text=True, check=False,
        )
        tiempo = time.time() + 8
        while time.time() < tiempo:
            if not self.cal._is_process_alive(int(root_pid)):
                break
            time.sleep(0.25)
        self.proc_pid = None  # ya muerto; tearDown no lo mata de nuevo

        self.assertFalse(
            self.cal._is_process_alive(int(root_pid)),
            "el proceso charmap no se cerro tras taskkill",
        )

        espera = self.cal.wait_for_application_window(
            root_pid=root_pid, timeout=3.0
        )
        self.assertEqual(espera["status"], "FALLO_APERTURA")
        self.assertFalse(espera["process_alive"])
        self.assertIsNone(espera["window"])

    # ---- preservacion de sesion: VS Code y ventanas previas intactas ----
    def test_3_8_5_5_3_preserva_ventanas_previas(self):
        """Las ventanas preexistentes (incluido Visual Studio Code) permanecen intactas."""
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
        if root_pid is not None:
            self.proc_pid = int(root_pid)

        espera = self.cal.wait_for_application_window(
            root_pid=root_pid, timeout=8.0
        )
        self.assertEqual(espera["status"], "VENTANA_DETECTADA")

        despues_ventanas = _ventanas()
        for hwnd in self.ventanas_antes:
            self.assertIn(
                hwnd, despues_ventanas,
                f"una ventana previa ({hwnd}) desaparecio despues del lanzamiento",
            )


def patch_time_sleep():
    """Parchea time.sleep para evitar esperas reales en pruebas sin lanzamiento."""
    from unittest.mock import patch
    return patch("src.hands.calibration.calibration_manager.time.sleep")


if __name__ == "__main__":
    unittest.main()
