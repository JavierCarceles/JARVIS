# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.5.4.

Comprueba contra el SO real que verify_visible_window_for_application
verifica que una ventana detectada es visible y corresponde a la aplicacion
solicitada, sin forzar foco, maximizar ni moverla, y sin confundirse con
Visual Studio Code.

La prueba usa una allowlist de una aplicacion inocua (charmap.exe / Mapa de
caracteres), la unica aplicacion del inventario local application_candidates
que pasa preflight real en este equipo. Registra una linea base de procesos y
ventanas, lanza con la API real (CalibrationManager.launch_application),
espera la ventana del proceso lanzado, verifica la ventana con la API real,
cierra SOLO lo creado por la prueba (por PID) y comprueba que Visual Studio
Code y las ventanas previas quedan intactas.

No se envia teclado ni raton a ninguna ventana. La ventana de charmap aparece
en el monitor primario (DISPLAY1), sin superponer Visual Studio Code, que
reside en la segunda pantalla (DISPLAY2).
"""

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


class TestVerificarVentanaVisibleAplicacionEntornoReal(unittest.TestCase):
    """3.8.5.5.4: verificar ventana visible y correspondiente a la aplicacion."""

    def setUp(self):
        self.cal = get_calibration_manager()
        self.preflight = get_application_preflight()
        self.screen_manager = get_screen_manager()
        self.charmap_antes = _contar_charmap()
        self.ventanas_antes = _ventanas()
        self.proc_pid = None
        self.hwnd_creado = None

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

    # ---- 3.8.5.5.4: ventana visible y correspondiente tras lanzar charmap ----
    def test_3_8_5_5_4_ventana_visible_correspondente_transparente(self):
        """Tras lanzar charmap, la ventana detectada es visible y corresponde."""
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

        # Esperar la ventana (3.8.5.5.3) y obtener la ventana detectada.
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

        # Verificar que la ventana detectada es visible y corresponde (3.8.5.5.4).
        verificacion = self.cal.verify_visible_window_for_application(
            ventana,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            root_pid=root_pid,
            owned_pids=getattr(self.cal, "_last_launch_owned_pids", set()),
        )
        self.hwnd_creado = verificacion["hwnd"]

        self.assertTrue(verificacion["verificada"], f"no verificada: {verificacion['reason']}")
        self.assertTrue(verificacion["visible"], "la ventana no es visible")
        self.assertTrue(verificacion["corresponde_aplicacion"], "no corresponde a la app")
        self.assertTrue(verificacion["criterio_pid"], "criterio PID no cumplido")
        # El criterio de nombre de proceso solo aplica cuando existe un
        # builtin de nombre de proceso para la aplicacion; para charmap /
        # "Mapa de caracteres" no hay builtin, asi que no es exigible aqui.
        self.assertIsNotNone(verificacion["hwnd"], "no se obtuvo HWND")
        self.assertEqual(verificacion["pid"], root_pid, "PID de ventana distinto al root_pid")
        self.assertFalse(
            verificacion["es_visual_studio_code"],
            "la ventana se confunde con Visual Studio Code",
        )
        self.assertEqual(verificacion["application_name"], _CHARMAP_NOMBRE)
        self.assertIn("correspondiente", verificacion["reason"])

        # No se forzo foco ni maximizar ni mover: la ventana sigue visible sin
        # haber sido alterada por la verificacion.
        self.assertTrue(self.cal._win32_is_visible(verificacion["hwnd"]))

        # Linea base de charmap: solo debe haber una instancia mas (la propia).
        despues = _contar_charmap()
        self.assertIn(
            despues, (self.charmap_antes, self.charmap_antes + 1),
            f"conteo charmap inesperado: antes={self.charmap_antes}, despues={despues}",
        )

    # ---- 3.8.5.5.4: ventana no corresponde a aplicacion ajena (ventana previa) ----
    def test_3_8_5_5_4_ventana_ajena_no_corresponde(self):
        """Una ventana previa ajena (p. ej. VS Code) no se verifica como charmap."""
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

        espera = self.cal.wait_for_application_window(
            root_pid=root_pid,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=8.0,
            poll_interval=0.4,
        )
        self.assertEqual(espera["status"], "VENTANA_DETECTADA")
        ventana_propia = espera["window"]
        hwnd_propia = self.cal._get_window_handle(ventana_propia)

        # Tomar una ventana previa ajena (la primera que no sea la creada por la prueba).
        ventana_ajena = None
        for w in self.cal._get_windows():
            hwnd = self.cal._get_window_handle(w)
            if hwnd and hwnd != hwnd_propia:
                ventana_ajena = w
                break
        self.assertIsNotNone(ventana_ajena, "no se encontro ninguna ventana previa ajena")

        verificacion_ajena = self.cal.verify_visible_window_for_application(
            ventana_ajena,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            root_pid=root_pid,
            owned_pids=getattr(self.cal, "_last_launch_owned_pids", set()),
        )
        # La ventana ajena no es de charmap: no debe verificarse como correspondiente.
        self.assertFalse(
            verificacion_ajena["verificada"],
            f"ventana ajena erroneamente verificada como charmap: {verificacion_ajena['reason']}",
        )
        self.assertFalse(verificacion_ajena["corresponde_aplicacion"])

    # ---- preservacion de sesion: VS Code y ventanas previas intactas ----
    def test_3_8_5_5_4_preserva_ventanas_previas(self):
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
            root_pid=root_pid,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=8.0,
            poll_interval=0.4,
        )
        self.assertEqual(espera["status"], "VENTANA_DETECTADA")

        despues_ventanas = _ventanas()
        for hwnd in self.ventanas_antes:
            self.assertIn(
                hwnd, despues_ventanas,
                f"una ventana previa ({hwnd}) desaparecio despues del lanzamiento",
            )


if __name__ == "__main__":
    unittest.main()
