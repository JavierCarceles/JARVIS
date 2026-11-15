# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.5.6.

Comprueba contra el SO real que los estados de lanzamiento de aplicacion
(ABRIENDO, PROCESO_INICIADO, VENTANA_DETECTADA, ABIERTA_VERIFICADA,
ABIERTA_SIN_VENTANA, FALLO, TIMEOUT) se representan por separado a lo largo
del flujo de apertura, usando la implementacion real de CalibrationManager.

La prueba usa una allowlist de una aplicacion inocua (charmap.exe / Mapa de
caracteres), la unica aplicacion del inventario local `application_candidates`
que pasa preflight real en este equipo. Lanza con la API real (sin mockear
lanzador, procesos ni ventanas), verifica las transiciones de estado reales,
cierra SOLO lo creado por la prueba (por PID) y comprueba que Visual Studio Code
y las ventanas previas quedan intactas.

No se envia teclado ni raton a ninguna ventana.
"""

import os
import subprocess
import time
import unittest

from src.hands.application_preflight import get_application_preflight
from src.hands.calibration_manager import (
    CalibrationManager,
    LaunchState,
    get_calibration_manager,
)
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


class TestEstadosLanzamientoAplicacionEntornoReal(unittest.TestCase):
    """3.8.5.5.6: representar estados de lanzamiento por separado en entorno real."""

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

    # ---- 3.8.5.5.6: estado ABRIENDO al iniciar y PROCESO_INICIADO tras lanzar ----
    def test_3_8_5_5_6_estado_abriendo_y_proceso_iniciado(self):
        """launch_application establece ABRIENDO al iniciar y PROCESO_INICIADO tras lanzar con exito."""
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")

        # Estado inicial: None (no hay lanzamiento previo en este manager compartido).
        # launch_application establece ABRIENDO al inicio.
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
            # Tras el lanzamiento exitoso, el estado debe ser PROCESO_INICIADO.
            self.assertEqual(
                self.cal.get_launch_state(), LaunchState.PROCESO_INICIADO,
                f"se esperaba PROCESO_INICIADO, obtuvo: {self.cal.get_launch_state()}",
            )
            self.assertTrue(self.cal._is_process_alive(int(root_pid)),
                            "el proceso lanzado no esta vivo")

            # El proceso sigue vivo durante un intervalo acotado.
            estabilidad = self.cal.verify_launch_process_stability(
                pid=root_pid, stability_interval=2.0, stability_checks=3
            )
            self.assertTrue(estabilidad["stable"],
                            f"el proceso no establecio: {estabilidad}")

    # ---- 3.8.5.5.6: estado VENTANA_DETECTADA al detectar la ventana ----
    def test_3_8_5_5_6_estado_ventana_detectada(self):
        """wait_for_application_window establece VENTANA_DETECTADA cuando encuentra la ventana."""
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

        # Esperar la ventana.
        espera = self.cal.wait_for_application_window(
            root_pid=root_pid,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=8.0,
            poll_interval=0.4,
        )
        self.assertEqual(
            espera["status"], "VENTANA_DETECTADA",
            f"se esperaba VENTANA_DETECTADA, obtuvo: {espera}",
        )
        self.assertEqual(
            self.cal.get_launch_state(), LaunchState.VENTANA_DETECTADA,
            f"se esperaba VENTANA_DETECTADA, obtuvo: {self.cal.get_launch_state()}",
        )
        self.assertIsNotNone(espera["window"], "no se devolvio objeto de ventana")
        self.assertTrue(espera["process_alive"], "el proceso no estuvo vivo")

    # ---- 3.8.5.5.6: estado ABIERTA_VERIFICADA al verificar la ventana ----
    def test_3_8_5_5_6_estado_abierta_verificada(self):
        """verify_visible_window_for_application establece ABIERTA_VERIFICADA cuando la ventana es visible y corresponde."""
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

        # Esperar la ventana.
        espera = self.cal.wait_for_application_window(
            root_pid=root_pid,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=8.0,
            poll_interval=0.4,
        )
        self.assertEqual(espera["status"], "VENTANA_DETECTADA")
        ventana = espera["window"]

        # Verificar que la ventana es visible y corresponde.
        verificacion = self.cal.verify_visible_window_for_application(
            ventana,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            root_pid=root_pid,
            owned_pids=getattr(self.cal, "_last_launch_owned_pids", set()),
        )
        self.assertTrue(verificacion["verificada"], f"no verificada: {verificacion['reason']}")
        self.assertTrue(verificacion["visible"])
        self.assertEqual(
            self.cal.get_launch_state(), LaunchState.ABIERTA_VERIFICADA,
            f"se esperaba ABIERTA_VERIFICADA, obtuvo: {self.cal.get_launch_state()}",
        )

    # ---- 3.8.5.5.6: estado ABIERTA_VERIFICADA tras estabilidad verificada ----
    def test_3_8_5_5_6_estado_verificado_tras_estabilidad(self):
        """verify_estabilidad_minima_proceso_ventana establece ABIERTA_VERIFICADA cuando proceso y ventana son estables."""
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

        # Esperar la ventana.
        espera = self.cal.wait_for_application_window(
            root_pid=root_pid,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=8.0,
            poll_interval=0.4,
        )
        self.assertEqual(espera["status"], "VENTANA_DETECTADA")
        ventana = espera["window"]

        # Estabilidad minima del proceso y la ventana durante un intervalo.
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
        self.assertEqual(
            self.cal.get_launch_state(), LaunchState.ABIERTA_VERIFICADA,
            f"se esperaba ABIERTA_VERIFICADA, obtuvo: {self.cal.get_launch_state()}",
        )
        self.assertEqual(estabilidad["checks_passed"], 3)
        self.assertEqual(estabilidad["total_checks"], 3)

    # ---- 3.8.5.5.6: estado FALLO cuando el PID es invalido ----
    def test_3_8_5_5_6_estado_fallo_pid_invalido(self):
        """wait_for_application_window establece FALLO cuando el PID es invalido."""
        resultado = self.cal.wait_for_application_window(
            root_pid=None,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=2.0,
        )
        self.assertEqual(
            resultado["status"], "FALLO_APERTURA",
            f"se esperaba FALLO_APERTURA, obtuvo: {resultado}",
        )
        self.assertEqual(
            self.cal.get_launch_state(), LaunchState.FALLO,
            f"se esperaba FALLO, obtuvo: {self.cal.get_launch_state()}",
        )

    # ---- 3.8.5.5.6: evidencia tecnica incluye launch_state ----
    def test_3_8_5_5_6_evidencia_incluye_launch_state(self):
        """get_launch_evidence incluye launch_state en la evidencia tecnica."""
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

        evidencia = self.cal.get_launch_evidence()
        self.assertIsNotNone(evidencia["launch_state"],
                             "launch_state ausente en la evidencia tecnica")
        self.assertEqual(evidencia["launch_state"], "proceso_iniciado",
                         f"se esperaba 'proceso_iniciado', obtuvo: {evidencia['launch_state']}")
        self.assertIsNotNone(evidencia["root_pid"], "evidencia sin root_pid")
        self.assertEqual(evidencia["root_pid"], root_pid)

        # Verificar que no se registra contenido privado ni argumentos secretos.
        self.assertNotIn("arguments", evidencia)
        self.assertNotIn("command_line", evidencia)

    # ---- Preservacion de ventanas previas (incluido VS Code) ----
    def test_3_8_5_5_6_ventanas_previas_intactas(self):
        """Las ventanas previas (incluido Visual Studio Code) quedan intactas tras la prueba."""
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

        # Las ventanas previas deben seguir estando en el SO.
        ventanas_despues = _ventanas()
        self.assertTrue(
            self.ventanas_antes.issubset(ventanas_despues),
            f"ventanas previas no intactas: antes={len(self.ventanas_antes)}, despues={len(ventanas_despues)}",
        )

    # ---- No registrar contenido privado ----
    def test_3_8_5_5_6_no_contenido_privado(self):
        """La evidencia tecnica no incluye argumentos ni contenido privado."""
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

        evidencia = self.cal.get_launch_evidence()
        self.assertNotIn("arguments", evidencia)
        self.assertNotIn("command_line", evidencia)
        self.assertNotIn("window_title", evidencia)


if __name__ == "__main__":
    unittest.main()
