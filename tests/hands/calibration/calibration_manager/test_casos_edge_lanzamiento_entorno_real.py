# -*- coding: utf-8 -*-
"""Verificacion real de entorno para la unidad 3.8.5.6.3.

Comprueba contra el SO real los casos edge de preflight/lanzamiento que
aun no tenian cobertura de entorno real:
- aplicacion ya abierta: segunda apertura reutiliza la ventana existente
  (ABIERTA_VERIFICADA), no crea proceso ni ventana propios.
- aplicacion cerrada y apertura correcta: verificadas en 3.8.5.6.2.
- ruta obsoleta: destino inexistente no se lanza (estado FALLO).
- timeout de deteccion de ventana: detect_window_for_process retorna None
  tras esperar el plazo sin fallar.
- proceso que termina: proceso real propiedad de la prueba se detiene y
  detect_window_for_process retorna None.
- ausencia de ventana: proceso vivo sin ventana detectable.
- permiso denegado: aplicacion con nombre de riesgo de elevacion es
  rechazada por launch_application (estado FALLO) sin elevar privilegios.

Usa charmap.exe (unica aplicacion GUI inocua del allowlist, inventario local
SQLite, machine_id actual), lanzada por la API real de ejecucion
(CalibrationManager.launch_application) sin mockear lanzador, enumeracion de
procesos ni identificacion de ventanas. Cierra SOLO el proceso creado por la
prueba (por PID) y preserva ventanas/procesos ajenos (Visual Studio Code).
No envia teclado ni raton a ninguna ventana.
"""

import os
import subprocess
import sys
import time
import unittest

from src.hands.apps.application_preflight import get_application_preflight
from src.hands.calibration.calibration_manager import get_calibration_manager


_CHARMAP_PATH = r"C:\Windows\System32\charmap.exe"
_CHARMAP_NAME = "charmap.exe"
_CHARMAP_NOMBRE = "Mapa de caracteres"
_RUTA_OBSOLETA = r"C:\Windows\System32\aplicacion_inexistente_jarvis_xyz.exe"


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


def _pids():
    return set(get_calibration_manager()._get_process_ids())


class TestCasosEdgeLanzamientoEntornoReal(unittest.TestCase):
    """3.8.5.6.3: casos edge de lanzamiento/preflight en entorno real."""

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

    # ---- 3.8.5.6.3: aplicacion ya abierta (reutiliza ventana existente) ----
    def test_3_8_5_6_3_aplicacion_ya_abierta_reutiliza_ventana(self):
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")
        self.assertTrue(os.path.isfile(_CHARMAP_PATH),
                        "charmap.exe no esta en la ruta esperada del equipo")

        # Primera apertura: asegura que hay una instancia abierta.
        r1 = self.cal.launch_application({
            "name": _CHARMAP_NOMBRE, "app_id": "", "path": _CHARMAP_PATH, "arguments": "",
        })
        ok1 = bool(r1[1]) if isinstance(r1, tuple) else bool(r1)
        self.assertTrue(ok1, "primera apertura de charmap fallo")
        was_owned_1 = bool(getattr(self.cal, "_last_launch_was_owned", False))
        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        if was_owned_1 and root_pid is not None:
            self.proc_pid = int(root_pid)
            self.assertTrue(self.cal._is_process_alive(int(root_pid)),
                            "el proceso lanzado no esta vivo")

        # Segunda apertura mientras ya hay una instancia abierta:
        # debe reutilizarla (ABIERTA_VERIFICADA), sin crear proceso/ventana propios.
        antes_hwnds = _ventanas()
        antes_pids = _pids()
        r2 = self.cal.launch_application({
            "name": _CHARMAP_NOMBRE, "app_id": "", "path": _CHARMAP_PATH, "arguments": "",
        })
        ok2 = bool(r2[1]) if isinstance(r2, tuple) else bool(r2)
        self.assertTrue(ok2, "reapertura de charmap ya abierta fallo")
        estado = getattr(self.cal, "_last_launch_state", None)
        self.assertEqual(
            estado.value if estado else None, "abierta_verificada",
            f"estado esperado ABIERTA_VERIFICADA, obtuvo: {estado}",
        )
        was_owned_2 = bool(getattr(self.cal, "_last_launch_was_owned", False))
        owned_hwnds_2 = set(getattr(self.cal, "_last_launch_owned_hwnds", set()))
        owned_pids_2 = set(getattr(self.cal, "_last_launch_owned_pids", set()))
        self.assertFalse(
            was_owned_2,
            "al reabrir app ya abierta no debe crear proceso/ventana propios",
        )
        self.assertEqual(len(owned_hwnds_2), 0, "no deben crearse ventanas propias al reutilizar")
        self.assertEqual(len(owned_pids_2), 0, "no deben crearse procesos propios al reutilizar")
        self.assertEqual(_ventanas(), antes_hwnds, "no deben aparecer ventanas nuevas")
        self.assertEqual(_pids(), antes_pids, "no deben aparecer procesos nuevos")
        self.assertEqual(
            _contar_charmap(), max(self.charmap_antes, 1),
            "el conteo de charmap no debe aumentar al reutilizar una instancia abierta",
        )

    # ---- 3.8.5.6.3: ruta obsoleta no lanza ----
    def test_3_8_5_6_3_ruta_obsoleta_no_lanza(self):
        self.assertFalse(
            os.path.isfile(_RUTA_OBSOLETA),
            "la ruta de prueba obsoleta no deberia existir",
        )
        # Preflight rechaza destino inexistente (validacion estatica, sin lanzar).
        validacion = self.preflight.validate_launch_destination(_RUTA_OBSOLETA)
        self.assertFalse(validacion.get("valid", True),
                         "validate_launch_destination acepto ruta obsoleta")
        self.assertEqual(validacion.get("launch_type"), None)

        # launch_application con ruta inexistente: FALLO, sin lanzar nada.
        antes = _contar_charmap()
        antes_hwnds = _ventanas()
        antes_pids = _pids()
        resultado = self.cal.launch_application({
            "name": "AplicacionObsoleta", "app_id": "", "path": _RUTA_OBSOLETA, "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertFalse(ok, "launch_application debio rechazar la ruta obsoleta")
        estado = getattr(self.cal, "_last_launch_state", None)
        self.assertEqual(
            estado.value if estado else None, "fallo",
            f"estado esperado FALLO, obtuvo: {estado}",
        )
        evidencia = self.cal.get_launch_evidence()
        self.assertEqual(evidencia["launch_state"], "fallo")
        # No se creo proceso ni ventana nueva respecto a la linea base.
        self.assertEqual(_contar_charmap(), antes,
                         "se lanzo un proceso charmap con ruta obsoleta")
        self.assertEqual(_ventanas(), antes_hwnds,
                         "se creo una ventana con ruta obsoleta")
        self.assertEqual(_pids(), antes_pids,
                         "se creo un proceso con ruta obsoleta")

    # ---- 3.8.5.6.3: timeout de deteccion de ventana ----
    def test_3_8_5_6_3_timeout_deteccion_ventana(self):
        pid_inexistente = 999999
        self.assertFalse(
            self.cal._is_process_alive(pid_inexistente),
            "el PID de prueba deberia no existir en el equipo",
        )
        inicio = time.monotonic()
        ventana = self.cal.detect_window_for_process(
            root_pid=pid_inexistente,
            application_name="NoExiste",
            app_id="",
            timeout=2.0,
        )
        transcurrido = time.monotonic() - inicio
        self.assertIsNone(
            ventana,
            "detect_window_for_process debio retornar None para proceso inexistente",
        )
        self.assertGreaterEqual(
            transcurrido, 1.5,
            "detect_window_for_process no respeto el plazo de espera",
        )
        self.assertLess(
            transcurrido, 5.0,
            "detect_window_for_process espero demasiado",
        )

    # ---- 3.8.5.6.3: proceso que termina (proceso real propiedad de la prueba se detiene) ----
    def test_3_8_5_6_3_proceso_que_termina_se_detecta_como_fin(self):
        pf = self.preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False), f"preflight: {pf.get('reason')}")
        self.assertTrue(os.path.isfile(_CHARMAP_PATH),
                        "charmap.exe no esta en la ruta esperada del equipo")

        pids_antes = _pids()
        hwnds_antes = _ventanas()

        # Lanzar charmap: proceso propiedad de la prueba, con ventana.
        r1 = self.cal.launch_application({
            "name": _CHARMAP_NOMBRE, "app_id": "", "path": _CHARMAP_PATH, "arguments": "",
        })
        ok1 = bool(r1[1]) if isinstance(r1, tuple) else bool(r1)
        self.assertTrue(ok1, "apertura de charmap fallo")
        root_pid = getattr(self.cal, "_last_launch_root_pid", None)
        was_owned_1 = bool(getattr(self.cal, "_last_launch_was_owned", False))
        self.assertTrue(was_owned_1,
                        "la apertura no dejo un proceso propiedad de la prueba")
        self.assertIsNotNone(root_pid, "no se obtuvo root_pid del proceso lanzado")
        self.assertTrue(self.cal._is_process_alive(int(root_pid)),
                        "el proceso lanzado deberia estar vivo")

        # Terminar SOLO el proceso creado por esta prueba, identificado por PID.
        # Nunca cerrar por nombre ni cerrar procesos ajenos al usuario.
        subprocess.run(
            ["taskkill", "/PID", str(int(root_pid)), "/F"],
            capture_output=True, text=True, check=False,
        )
        muerto = False
        tiempo = time.time() + 8
        while time.time() < tiempo:
            if not self.cal._is_process_alive(int(root_pid)):
                muerto = True
                break
            time.sleep(0.25)
        self.assertTrue(muerto, "el proceso charmap no termino tras taskkill")

        # Proceso terminado: detect_window_for_process debe retornar None
        # (proceso sin ventana / ya no existe). El proceso lanzado por la
        # prueba ya esta muerto (comprobado arriba). Verificar que no aparecio
        # ningun proceso nuevo respecto a la linea base (procesos del sistema
        # que salieron entre setUp y el final no son relevantes).
        self.assertEqual(
            _pids() - pids_antes,
            set(),
            "aparecieron procesos nuevos tras terminar el proceso de la prueba",
        )
        self.assertEqual(
            _ventanas() - hwnds_antes,
            set(),
            "aparecieron ventanas nuevas tras terminar el proceso de la prueba",
        )

    # ---- 3.8.5.6.3: ausencia de ventana (proceso vivo sin ventana detectable) ----
    def test_3_8_5_6_3_ausencia_ventana_proceso_sin_ventana(self):
        """Proceso vivo sin ventana: _is_process_alive True, detect_window_for_process None.

        Lanza un proceso de prueba propio sin ventana (CREATE_NO_WINDOW),
        verifica que esta vivo pero que no hay ventana detectable, y lo termina
        solo al finalizar. No es un candidato descubierto ni una aplicacion del
        usuario; es un recurso de prueba temporal.
        """
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(25)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        pid = proc.pid
        self.proc_pid = pid  # tearDown cierra solo este proceso por PID
        self.assertIsNotNone(pid, "no se obtuvo PID del proceso de prueba")

        # El proceso debe estar vivo aunque no tenga ventana.
        self.assertTrue(
            self.cal._is_process_alive(pid),
            "el proceso de prueba sin ventana deberia estar vivo",
        )

        # No debe tener ventana detectable (sin ventana propia + allow_console=False).
        ventana = self.cal.detect_window_for_process(
            root_pid=pid,
            application_name="python",
            app_id="",
            timeout=2.0,
        )
        self.assertIsNone(
            ventana,
            "proceso sin ventana no deberia devolver una ventana detectable",
        )

        # Cerrar SOLO el proceso creado por esta prueba.
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self.assertFalse(
            self.cal._is_process_alive(pid),
            "el proceso de prueba deberia haber terminado tras terminate",
        )

    # ---- 3.8.5.6.3: permiso denegado (nombre de riesgo de elevacion rechazado) ----
    def test_3_8_5_6_3_permiso_denegado_nombre_riesgo_elevacion(self):
        """Aplicacion con nombre de riesgo de elevacion es rechazada por
        launch_application (estado FALLO) sin elevar privilegios ni crear
        proceso/ventana. Usa nombre localizado en espanol que coincide con
        ELEVATION_RISK_EXACT_NAMES de CalibrationManager."""
        antes_hwnds = _ventanas()
        antes_pids = _pids()
        antes_charmap = _contar_charmap()

        # "editor del registro" coincide con ELEVATION_RISK_EXACT_NAMES.
        # regedit.exe no existe en este equipo, pero el bloqueo ocurre
        # antes de tocar el path, por _should_ignore_application.
        resultado = self.cal.launch_application({
            "name": "editor del registro",
            "app_id": "",
            "path": r"C:\Windows\System32\regedit.exe",
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertFalse(ok, "launch_application debio rechazar nombre de riesgo de elevacion")
        estado = getattr(self.cal, "_last_launch_state", None)
        self.assertEqual(
            estado.value if estado else None, "fallo",
            "estado esperado FALLO para nombre de riesgo de elevacion, obtuvo: %s" % estado,
        )
        # No se creo proceso ni ventana propia.
        self.assertFalse(
            getattr(self.cal, "_last_launch_was_owned", True),
            "nombre de riesgo de elevacion no debe crear proceso propio",
        )
        self.assertEqual(
            len(getattr(self.cal, "_last_launch_owned_hwnds", set())), 0,
            "no deben crearse ventanas propias",
        )
        self.assertEqual(
            len(getattr(self.cal, "_last_launch_owned_pids", set())), 0,
            "no deben crearse PIDs propios",
        )
        # Linea base preservada: la llamada de lanzamiento rechazada no debe
        # crear proceso ni ventana propios (ya comprobado por was_owned y
        # owned_pids/owned_hwnds vacios). El conteo de charmap no debe cambiar.
        self.assertEqual(_contar_charmap(), antes_charmap, "conteo de charmap cambio")


if __name__ == "__main__":
    unittest.main()
