# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.5.2.

Comprueba contra el SO real que, tras lanzar una aplicacion GUI cerrada
mediante la API real de ejecucion (CalibrationManager.launch_application),
es posible detectar la ventana perteneciente al proceso objetivo mediante
identificadores (PID, arbol de procesos) y propietario (relacion HWND owner),
sin aceptar coincidencia basada solo en el titulo.

La prueba usa una allowlist de una aplicacion inocua (charmap.exe / Mapa de
caracteres), la unica aplicacion del inventario local `application_candidates`
que pasa preflight real en este equipo. Registra una linea base de procesos y
ventanas, lanza con la API real (sin mockear lanzador, procesos ni ventanas),
detecta la ventana del proceso lanzado, verifica que el PID de la ventana
coincide con el PID del proceso, cierra SOLO lo creado por la prueba y
comprueba que Visual Studio Code y las ventanas previas quedan intactas.

No se envia teclado ni raton a ninguna ventana.
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


class TestDetectarVentanaPorProcesoEntornoReal(unittest.TestCase):
    """3.8.5.5.2: detectar ventana perteneciente al proceso por ID y propietario."""

    def setUp(self):
        self.cal = get_calibration_manager()
        self.preflight = get_application_preflight()
        self.charmap_antes = _contar_charmap()
        self.ventanas_antes = _ventanas()
        self.proc_pid = None
        self.ventana_hwnd = None

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

    # ---- 3.8.5.5.2: detectar ventana por PID y propietario ----
    def test_3_8_5_5_2_detectar_ventana_por_pid_y_propietario(self):
        """Tras lanzar charmap, detect_window_for_process encuentra su ventana."""
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

        self.assertTrue(was_owned, "charmap no fue lanzado como proceso propio")
        self.assertIsNotNone(root_pid, "no se obtuvo root_pid del lanzamiento")
        self.proc_pid = int(root_pid)

        # El proceso debe estar vivo justo despues del lanzamiento.
        self.assertTrue(
            self.cal._is_process_alive(int(root_pid)),
            "el proceso lanzado no esta vivo justo despues del lanzamiento",
        )

        # Detectar la ventana perteneciente al proceso (PID + propietario).
        ventana = self.cal.detect_window_for_process(
            root_pid=int(root_pid),
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=8.0,
        )

        self.assertIsNotNone(
            ventana, "no se detecto ventana perteneciente al proceso charmap"
        )
        self.ventana_hwnd = self.cal._get_window_handle(ventana)
        self.assertIsNotNone(self.ventana_hwnd, "la ventana detectada no tiene HWND")

        # El PID de la ventana detectada debe coincidir con el PID del proceso.
        ventana_pid = self.cal._get_window_process_id(ventana)
        self.assertIsNotNone(ventana_pid, "la ventana detectada no tiene PID")
        self.assertIn(
            ventana_pid, owned_pids,
            f"el PID de la ventana ({ventana_pid}) no esta en los PIDs propios del lanzamiento ({owned_pids})",
        )

        # La ventana debe ser visible.
        self.assertTrue(
            self.cal._win32_is_visible(self.ventana_hwnd),
            "la ventana detectada no es visible",
        )

        # Linea base de charmap: solo debe haber una instancia mas (la propia).
        despues = _contar_charmap()
        self.assertIn(
            despues, (self.charmap_antes, self.charmap_antes + 1),
            f"conteo charmap inesperado: antes={self.charmap_antes}, despues={despues}",
        )

    # ---- 3.8.5.5.2: coincidencia solo por titulo NO es suficiente ----
    def test_3_8_5_5_2_titulo_sin_pid_no_es_suficiente(self):
        """Proveer un application_name que coincida con el titulo pero un PID
        inexistente/no relacionado no debe detectar la ventana de charmap."""
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

        # Pedir deteccion con un PID que no pertenece a charmap (999999)
        # pero con un application_name que coincida con el titulo.
        # Como el PID no pertenece al proceso lanzado, no debe detectarse.
        ventana = self.cal.detect_window_for_process(
            root_pid=999999,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=2.0,
        )
        self.assertIsNone(
            ventana,
            "no se debe detectar ventana cuando el PID no pertenece al proceso objetivo "
            "aunque el nombre de la aplicaci\u00f3n coincida",
        )

    # ---- preservacion de sesion: VS Code y ventanas previas intactas ----
    def test_3_8_5_5_2_preserva_ventanas_previas(self):
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

        # Las ventanas previas deben seguir estando presentes.
        despues_ventanas = _ventanas()
        for hwnd in self.ventanas_antes:
            self.assertIn(
                hwnd, despues_ventanas,
                f"una ventana previa ({hwnd}) desaparecio despues del lanzamiento",
            )


if __name__ == "__main__":
    unittest.main()
