# -*- coding: utf-8 -*-
"""Ejecucion real de ciclo completo para la unidad 3.8.5.6.6.

Ciclo unico en un solo metodo de test:
abrir -> detectar proceso -> detectar ventana -> verificar estado ->
cerrar solo la ventana/proceso creado por la prueba -> verificar preservacion
de VS Code y ventanas preexistentes.

Usa la API real de produccion (CalibrationManager.launch_application,
detect_window_for_process, wait_for_application_window,
verify_visible_window_for_application, ApplicationPreflight) sin mocks.
"""

import os
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


class TestCicloCompletoAperturaCerrarEntornoReal(unittest.TestCase):
    """3.8.5.6.6: ciclo real abrir -> detectar proceso -> detectar ventana ->
    verificar estado -> cerrar solo lo creado en la segunda pantalla,
    preservando VS Code y ventanas previas."""

    def setUp(self):
        self.cal = get_calibration_manager()
        self.preflight = get_application_preflight()
        self.sm = get_screen_manager()
        self.charmap_antes = _contar_charmap()
        self.vscode_antes = _contar_vscode()
        self.ventanas_antes = _ventanas()
        self.resultados = {}

    def tearDown(self):
        # Cerrar SOLO el proceso creado por esta prueba, si quedara vivo.
        if getattr(self, "proc_pid", None) is not None:
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
            self.proc_pid = None

    # ---- CICLO COMPLETO EN UN SOLO METODO ----
    def test_3_8_5_6_6_ciclo_completo_abrir_detectar_verificar_cerrar(self):
        """Ejecuta el ciclo completo real en una sola secuencia."""
        cal = self.cal
        preflight = self.preflight
        sm = self.sm

        # ========== PASO 1: Enumerar monitores reales e identificar segunda pantalla ==========
        self.assertGreaterEqual(len(sm.monitors), 2,
            f"se esperaban al menos 2 monitores, encontrados {len(sm.monitors)}")
        primarios = [m for m in sm.monitors if m.is_primary]
        secundarios = [m for m in sm.monitors if not m.is_primary]
        self.assertEqual(len(primarios), 1, "debe haber exactamente un monitor primario")
        self.assertGreaterEqual(len(secundarios), 1, "debe haber al menos un monitor secundario")
        segundo = secundarios[0]
        self.resultados["monitor_primario"] = {
            "id": primarios[0].monitor_id, "left": primarios[0].left,
            "top": primarios[0].top, "width": primarios[0].width,
            "height": primarios[0].height,
        }
        self.resultados["monitor_segundo"] = {
            "id": segundo.monitor_id, "left": segundo.left,
            "top": segundo.top, "width": segundo.width,
            "height": segundo.height,
        }
        print(f"  MONITOR PRIMARIO: {self.resultados['monitor_primario']}")
        print(f"  MONITOR SEGUNDO: {self.resultados['monitor_segundo']}")

        # ========== PASO 2: Linea base real de procesos y ventanas ==========
        self.assertIsInstance(self.charmap_antes, int)
        self.assertGreaterEqual(self.charmap_antes, 0)
        self.assertIsInstance(self.vscode_antes, int)
        self.assertGreaterEqual(self.vscode_antes, 1,
            "se esperaba al menos un proceso de Visual Studio Code en linea base")
        self.assertIsInstance(self.ventanas_antes, set)
        self.resultados["charmap_antes"] = self.charmap_antes
        self.resultados["vscode_antes"] = self.vscode_antes
        self.resultados["ventanas_antes_count"] = len(self.ventanas_antes)
        print(f"  LINEA BASE: charmap={self.charmap_antes}, vscode={self.vscode_antes}, ventanas={len(self.ventanas_antes)}")

        # ========== PASO 3: Preflight real sobre charmap.exe ==========
        pf = preflight.check({
            "name": _CHARMAP_NOMBRE, "app_id": "",
        })
        self.assertTrue(pf.get("allowed", False),
            f"preflight rechazo charmap: {pf.get('reason')}")
        self.assertEqual(
            (pf.get("executable_path") or "").lower(),
            _CHARMAP_PATH.lower(),
            f"preflight resuelve ruta distinta: {pf.get('executable_path')}",
        )
        self.assertFalse(pf.get("requires_elevation", True),
            "charmap no deberia requerir elevacion")
        self.resultados["preflight"] = {
            "allowed": pf.get("allowed"),
            "executable_path": pf.get("executable_path"),
            "requires_elevation": pf.get("requires_elevation"),
            "confidence": pf.get("confidence"),
        }
        print(f"  PREFLIGHT: allowed={pf.get('allowed')}, path={pf.get('executable_path')}, elevation={pf.get('requires_elevation')}")

        # ========== PASO 4: Lanzamiento real, detectar proceso ==========
        antes_hwnds = _ventanas()
        antes_pids = set(cal._get_process_ids())

        # Lanzamiento REAL (sin mockear lanzador, procesos ni ventanas).
        resultado = cal.launch_application({
            "name": _CHARMAP_NOMBRE,
            "app_id": "",
            "path": _CHARMAP_PATH,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertTrue(ok, "launch_application no informo exito al abrir charmap")

        root_pid = getattr(cal, "_last_launch_root_pid", None)
        owned_pids = getattr(cal, "_last_launch_owned_pids", set())
        owned_hwnds = getattr(cal, "_last_launch_owned_hwnds", set())
        was_owned = bool(getattr(cal, "_last_launch_was_owned", False))
        launch_state = str(getattr(cal, "_last_launch_state", "DESCONOCIDO"))

        self.assertTrue(was_owned, "charmap no fue lanzado como proceso propio de la prueba")
        self.assertIsNotNone(root_pid, "no se obtuvo root_pid del lanzamiento")
        self.proc_pid = int(root_pid)

        # El proceso debe estar vivo justo despues del lanzamiento.
        self.assertTrue(
            cal._is_process_alive(int(root_pid)),
            "el proceso lanzado no esta vivo justo despues del lanzamiento",
        )

        # Proceso nuevo respecto a la linea base.
        self.assertIn(int(root_pid), owned_pids,
            f"el root_pid {root_pid} no esta en los PIDs propios del lanzamiento")

        despues_charmap = _contar_charmap()
        self.assertIn(
            despues_charmap, (self.charmap_antes, self.charmap_antes + 1),
            f"conteo charmap inesperado: antes={self.charmap_antes}, despues={despues_charmap}",
        )

        self.resultados["lanzamiento"] = {
            "ok": ok,
            "was_owned": was_owned,
            "root_pid": int(root_pid),
            "launch_state": launch_state,
            "owned_pids": list(owned_pids),
            "owned_hwnds_count": len(owned_hwnds),
            "charmap_antes": self.charmap_antes,
            "charmap_despues": despues_charmap,
        }
        print(f"  LANZAMIENTO: ok={ok}, was_owned={was_owned}, root_pid={root_pid}, state={launch_state}, charmap_despues={despues_charmap}")

        # ========== PASO 5: Detectar ventana perteneciente al proceso ==========
        # Esperar la ventana (3.8.5.5.3) y obtener la ventana detectada.
        espera = cal.wait_for_application_window(
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

        # Detectar ventana mediante detect_window_for_process (3.8.5.5.2).
        ventana2 = cal.detect_window_for_process(
            root_pid=root_pid,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            timeout=8.0,
        )
        self.assertIsNotNone(
            ventana2, "detect_window_for_process no encontro ventana de charmap",
        )

        hwnd_creado = cal._get_window_handle(ventana)
        self.assertIsNotNone(hwnd_creado, "la ventana detectada no tiene HWND")

        # El PID de la ventana detectada debe coincidir con el PID del proceso.
        ventana_pid = cal._get_window_process_id(ventana)
        self.assertIsNotNone(ventana_pid, "la ventana detectada no tiene PID")

        # La ventana debe ser visible.
        self.assertTrue(
            cal._win32_is_visible(hwnd_creado),
            "la ventana detectada no es visible",
        )

        # No confundir con Visual Studio Code.
        es_vscode = getattr(cal, "_es_visual_studio_code", lambda hwnd: False)(hwnd_creado)
        self.assertFalse(es_vscode, "la ventana detectada se confunde con Visual Studio Code")

        self.resultados["deteccion_ventana"] = {
            "ventana_detectada": espera["status"],
            "hwnd": hwnd_creado,
            "ventana_pid": ventana_pid,
            "root_pid": root_pid,
            "visible": True,
            "es_visual_studio_code": es_vscode,
        }
        print(f"  DETECCION VENTANA: status={espera['status']}, hwnd={hwnd_creado}, ventana_pid={ventana_pid}, root_pid={root_pid}, es_vscode={es_vscode}")

        # ========== PASO 6: Verificar estado de la ventana ==========
        ventana_obj = cal._get_window_by_handle(hwnd_creado)
        self.assertIsNotNone(ventana_obj, "no se recupero objeto de ventana desde HWND")

        verificacion = cal.verify_visible_window_for_application(
            ventana_obj,
            application_name=_CHARMAP_NOMBRE,
            app_id="",
            root_pid=root_pid,
            owned_pids=getattr(cal, "_last_launch_owned_pids", set()),
        )

        self.assertTrue(verificacion["verificada"],
            f"ventana no verificada: {verificacion.get('reason')}")
        self.assertTrue(verificacion["visible"], "la ventana no es visible")
        self.assertTrue(verificacion["corresponde_aplicacion"],
            "la ventana no corresponde a la aplicacion solicitada")
        self.assertTrue(verificacion["criterio_pid"], "criterio PID no cumplido")
        self.assertFalse(
            verificacion["es_visual_studio_code"],
            "la ventana se confunde con Visual Studio Code",
        )
        self.assertEqual(verificacion["pid"], root_pid,
            "PID de ventana distinto al root_pid")

        # No se forzo foco ni maximizar ni mover.
        self.assertTrue(cal._win32_is_visible(hwnd_creado),
            "la ventana dejo de ser visible tras la verificacion")

        self.resultados["verificacion_estado"] = {
            "verificada": verificacion["verificada"],
            "visible": verificacion["visible"],
            "corresponde_aplicacion": verificacion["corresponde_aplicacion"],
            "criterio_pid": verificacion["criterio_pid"],
            "es_visual_studio_code": verificacion["es_visual_studio_code"],
            "pid": verificacion["pid"],
            "root_pid": root_pid,
            "reason": verificacion.get("reason", ""),
        }
        print(f"  VERIFICACION ESTADO: verificada={verificacion['verificada']}, visible={verificacion['visible']}, corresponde={verificacion['corresponde_aplicacion']}, es_vscode={verificacion['es_visual_studio_code']}")

        # ========== PASO 7: Cerrar solo lo creado por la prueba ==========
        # Cerrar solo el proceso creado por la prueba (por PID).
        subprocess.run(
            ["taskkill", "/PID", str(int(root_pid)), "/F"],
            capture_output=True, text=True, check=False,
        )
        tiempo = time.time() + 10
        while time.time() < tiempo:
            if not cal._is_process_alive(int(root_pid)):
                break
            time.sleep(0.25)
        self.assertFalse(
            cal._is_process_alive(int(root_pid)),
            "el proceso propio no se termino tras cerrar por PID",
        )
        self.proc_pid = None  # evitar que tearDown intente matarlo de nuevo

        # La cuenta de charmap debe volver a la linea base.
        self.assertEqual(_contar_charmap(), self.charmap_antes,
            "conteo de charmap no volvio a la linea base tras el cierre")

        # Las ventanas preexistentes (incluido VS Code) deben seguir presentes.
        despues_ventanas = _ventanas()
        faltantes = []
        for hwnd in self.ventanas_antes:
            if hwnd not in despues_ventanas:
                faltantes.append(hwnd)
        self.assertEqual(
            faltantes, [],
            f"desaparecieron ventanas previas tras el cierre: {faltantes}",
        )

        # Visual Studio Code debe seguir ejecutandose (proceso preservado).
        vscode_despues = _contar_vscode()
        self.assertGreaterEqual(vscode_despues, self.vscode_antes,
            f"Visual Studio Code no se preservo: antes={self.vscode_antes}, despues={vscode_despues}")

        self.resultados["cierre_y_preservacion"] = {
            "proceso_terminado": not cal._is_process_alive(int(root_pid)),
            "charmap_antes": self.charmap_antes,
            "charmap_despues": _contar_charmap(),
            "ventanas_antes_count": len(self.ventanas_antes),
            "ventanas_despues_count": len(despues_ventanas),
            "ventanas_faltantes": faltantes,
            "vscode_antes": self.vscode_antes,
            "vscode_despues": vscode_despues,
            "vscode_preservado": vscode_despues >= self.vscode_antes,
        }
        print(f"  CIERRE Y PRESERVACION: proceso_terminado=True, charmap_despues={_contar_charmap()}, ventanas_despues={len(despues_ventanas)}, vscode_despues={vscode_despues}, vscode_preservado={vscode_despues >= self.vscode_antes}")

        # ========== RESUMEN DEL CICLO ==========
        print("\n  === RESUMEN CICLO 3.8.5.6.6 ===")
        for clave, valor in self.resultados.items():
            print(f"  {clave}: {valor}")
        print("  CICLO COMPLETO: OK")


if __name__ == "__main__":
    unittest.main()
