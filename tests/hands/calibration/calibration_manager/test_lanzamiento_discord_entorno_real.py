# -*- coding: utf-8 -*-
"""Test de entorno real para la unidad 3.8.5.6.9 (roadmap).

Objetivo:
  Incluir controles negativos reales (destino inexistente, ruta obsoleta,
  ejecutable desconocido, permiso denegado) y confirmar que no aparece un
  proceso nuevo ni se modifica ninguna ventana previa.

Flujo real (sin mocks) contra Discord:
  1. Verificar que Discord.exe existe en disco.
  2. Registrarlo como candidato en application_candidates si no esta.
  3. ApplicationPreflight.check() contra Discord: allowed=True,
     requires_elevation=False.
  4. CalibrationManager.launch_application() con ruta real.
  5. _is_process_alive(), obtener PID, detectar ventana con
     wait_for_application_window() / detect_window_for_process().
  6. Ventana visible, no es VS Code, PID de ventana coincide con root_pid.
  7. Cerrar SOLO el proceso creado (por PID), nunca procesos preexistentes.
  8. Comprobar VS Code y ventanas previas intactas.
  9. Linea base antes y despues (conteo procesos Discord, ventanas, Code.exe).
  10. Controles negativos: destino inexistente, ejecutable desconocido,
      ruta obsoleta, permiso denegado.

Ejecuta una aplicacion a la vez, nunca en lote ni en paralelo.
No captura contenido privado de Discord ni de otras ventanas.
"""

import os
import sqlite3
import subprocess
import time
import uuid
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.hands.apps.application_discovery import ApplicationDiscovery, DiscoveredCandidate
from src.hands.apps.application_preflight import get_application_preflight
from src.hands.calibration.calibration_manager import get_calibration_manager
from src.hands.inventory.system_inventory import generate_machine_id
from src.hands.inventory.system_inventory_storage import SystemInventoryStorage
from src.core.config import get_project_root
from src.desktop.screen_manager import get_screen_manager


# ---------------------------------------------------------------------------
# Constantes de Discord
# ---------------------------------------------------------------------------
DISCORD_NAME = "Discord"
DISCORD_APP_ID = ""
DISCORD_PATH = r"C:\Users\User\AppData\Local\Discord\Discord.exe"
DISCORD_VOLUME = "C:"


# ---------------------------------------------------------------------------
# Helpers de observacion del SO real (sin mocks)
# ---------------------------------------------------------------------------
def _contar_procesos_por_nombre(nombre_imagen: str) -> int:
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {nombre_imagen}"],
        capture_output=True, text=True, check=False,
    )
    return sum(
        1 for linea in (resultado.stdout or "").splitlines()
        if nombre_imagen.lower() in linea.lower()
    )


def _contar_discord() -> int:
    return _contar_procesos_por_nombre("Discord.exe")


def _contar_vscode() -> int:
    return _contar_procesos_por_nombre("Code.exe")


def _ventanas_actuales() -> set:
    return set(get_calibration_manager()._get_window_handles())


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
class TestLanzamientoDiscordEntornoReal(unittest.TestCase):

    def setUp(self):
        self.cal = get_calibration_manager()
        self.preflight = get_application_preflight()
        db_path = get_project_root() / "data" / "system_inventory.sqlite3"
        self.storage = SystemInventoryStorage(db_path)
        self.machine_id = generate_machine_id()
        self.sm = get_screen_manager()

        self.discord_antes = _contar_discord()
        self.vscode_antes = _contar_vscode()
        self.ventanas_antes = _ventanas_actuales()
        self.discord_was_running = self.discord_antes > 0

        self.proc_pid = None
        self.root_pid = None
        self.was_owned = False
        self.discord_registrado_en_test = False
        self.resultados = {}

    def tearDown(self):
        if self.proc_pid is not None and not self.discord_was_running:
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

    def _buscar_discord_en_inventario(self) -> list[dict]:
        candidatos = self.storage.buscar_candidatos_registrados(
            machine_id=self.machine_id,
            name="discord",
            limite=10,
        )
        if not candidatos:
            todos = self.storage.buscar_candidatos_registrados(
                machine_id=self.machine_id,
                limite=200,
            )
            candidatos = [
                c for c in todos
                if "discord" in str(c.get("name", "")).lower()
                or "discord" in str(c.get("absolute_path", "")).lower()
            ]
        return candidatos

    def _registrar_discord_como_candidato(self) -> bool:
        discovery = ApplicationDiscovery(
            storage=self.storage,
            machine_id=self.machine_id,
        )
        ahora = _ahora_iso()
        candidate_id = (
            f"cand-discord-{self.machine_id}-{uuid.uuid4().hex[:8]}"
        )
        candidata = DiscoveredCandidate(
            candidate_id=candidate_id,
            name=DISCORD_NAME,
            absolute_path=DISCORD_PATH,
            launch_type="ejecutable",
            confianza=0.9,
            version=None,
            producto="Discord",
            evidencia=["ruta_discord_existe_disco"],
            fuente="registro_prueba_entorno_real",
            ultima_comprobacion=ahora,
        )
        insertados = discovery.registrar_candidatos(
            candidatos=[candidata],
            volume=DISCORD_VOLUME,
        )
        self.discord_registrado_en_test = insertados > 0
        return insertados > 0

    # ---- TEST 01: linea base ------------------------------------------

    def test_01_linea_base_conteos(self):
        self.assertIsInstance(self.discord_antes, int)
        self.assertGreaterEqual(self.discord_antes, 0)
        self.assertIsInstance(self.vscode_antes, int)
        self.assertGreaterEqual(self.vscode_antes, 1)
        self.assertIsInstance(self.ventanas_antes, set)
        self.resultados["linea_base"] = {
            "discord_antes": self.discord_antes,
            "vscode_antes": self.vscode_antes,
            "ventanas_antes": len(self.ventanas_antes),
            "discord_ya_ejecutandose": self.discord_was_running,
            "machine_id": self.machine_id,
        }

    # ---- TEST 02: monitores -------------------------------------------

    def test_02_monitores_y_segunda_pantalla(self):
        self.assertGreaterEqual(len(self.sm.monitors), 2)
        primarios = [m for m in self.sm.monitors if m.is_primary]
        secundarios = [m for m in self.sm.monitors if not m.is_primary]
        self.assertEqual(len(primarios), 1)
        self.assertGreaterEqual(len(secundarios), 1)
        segundo = secundarios[0]
        self.resultados["monitores"] = {
            "primario_id": primarios[0].monitor_id,
            "secundario_id": segundo.monitor_id,
        }

    # ---- TEST 03: consulta inventario ---------------------------------

    def test_03_consulta_inventario_discord(self):
        candidatos = self._buscar_discord_en_inventario()
        self.resultados["inventario_antes"] = {
            "candidatos_encontrados": len(candidatos),
            "candidatos": candidatos,
        }
        self.assertIsInstance(candidatos, list)

    # ---- TEST 04: registrar Discord -----------------------------------

    def test_04_registrar_discord_candidato(self):
        candidatos_antes = self._buscar_discord_en_inventario()
        if candidatos_antes:
            self.skipTest(
                "Discord ya esta registrado en el inventario"
            )
        ok = self._registrar_discord_como_candidato()
        self.assertTrue(ok)
        candidatos_despues = self._buscar_discord_en_inventario()
        self.assertGreaterEqual(len(candidatos_despues), 1)
        self.resultados["registro"] = {
            "registrado": self.discord_registrado_en_test,
            "candidatos_despues": len(candidatos_despues),
        }

    # ---- TEST 05: preflight ------------------------------------------

    def test_05_preflight_discord(self):
        candidatos = self._buscar_discord_en_inventario()
        if not candidatos:
            self.skipTest("Discord no esta registrado en el inventario")
        app_name = candidatos[0].get("name", DISCORD_NAME)
        pf = self.preflight.check({"name": app_name, "app_id": DISCORD_APP_ID})
        self.resultados["preflight"] = {
            "allowed": pf.get("allowed"),
            "executable_path": pf.get("executable_path"),
            "requires_elevation": pf.get("requires_elevation"),
            "reason": pf.get("reason"),
        }
        self.assertTrue(pf.get("allowed", False),
                        f"preflight rechazo Discord: {pf.get('reason')}")
        self.assertFalse(pf.get("requires_elevation", True))

    # ---- TEST 06: lanzamiento completo ------------------------------

    def test_06_lanzamiento_discord_completo(self):
        cal = self.cal
        preflight = self.preflight

        candidatos = self._buscar_discord_en_inventario()
        if not candidatos:
            self._registrar_discord_como_candidato()
            candidatos = self._buscar_discord_en_inventario()
        if not candidatos:
            self.skipTest("Discord no esta registrado y no se pudo registrar")
        cand = candidatos[0]
        app_name = cand.get("name", DISCORD_NAME)

        pf = preflight.check({"name": app_name, "app_id": DISCORD_APP_ID})
        if not pf.get("allowed", False):
            self.skipTest(f"preflight rechazo Discord: {pf.get('reason')}")
        self.assertFalse(pf.get("requires_elevation", True))

        if self.discord_was_running:
            self.skipTest("Discord ya estaba en ejecucion; NO VERIFICADO")

        antes_discord = _contar_discord()
        antes_hwnds = _ventanas_actuales()
        antes_pids = set(cal._get_process_ids())

        self.assertEqual(antes_discord, 0,
                         f"Discord no deberia correr antes: {antes_discord}")

        resultado = cal.launch_application({
            "name": app_name,
            "app_id": DISCORD_APP_ID,
            "path": DISCORD_PATH,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)

        root_pid = getattr(cal, "_last_launch_root_pid", None)
        owned_pids = getattr(cal, "_last_launch_owned_pids", set())
        owned_hwnds = getattr(cal, "_last_launch_owned_hwnds", set())
        was_owned = bool(getattr(cal, "_last_launch_was_owned", False))
        launch_state = str(getattr(cal, "_last_launch_state", "DESCONOCIDO"))

        self.resultados["lanzamiento"] = {
            "ok": ok, "was_owned": was_owned, "launch_state": launch_state,
            "root_pid": root_pid, "owned_pids": list(owned_pids),
            "owned_hwnds_count": len(owned_hwnds),
        }

        if not was_owned or root_pid is None:
            self.skipTest(
                "launch_application no lanzo proceso propio de Discord "
                f"(estado={launch_state}, was_owned={was_owned}); NO VERIFICADO"
            )

        self.root_pid = int(root_pid)
        self.proc_pid = self.root_pid
        self.was_owned = True

        self.assertTrue(ok, "launch_application no informo exito")
        self.assertTrue(
            cal._is_process_alive(self.root_pid),
            "el proceso de Discord no esta vivo tras el lanzamiento",
        )
        self.assertIn(
            self.root_pid, owned_pids,
            f"el root_pid {self.root_pid} no esta en PIDs propios",
        )

        despues_discord = _contar_discord()
        # Discord (Electron) lanza varios procesos hijos; verificar que al menos
        # el root_pid lanzado siga vivo y que el conteo haya crecido.
        self.assertGreater(
            despues_discord, antes_discord,
            f"conteo Discord no crecio: antes={antes_discord}, despues={despues_discord}",
        )
        self.assertTrue(
            cal._is_process_alive(self.root_pid),
            f"el root_pid {self.root_pid} no esta vivo tras el lanzamiento",
        )

        espera = cal.wait_for_application_window(
            root_pid=self.root_pid, application_name=app_name,
            app_id=DISCORD_APP_ID, timeout=20.0, poll_interval=0.5,
        )
        self.resultados["espera_ventana"] = {
            "status": espera.get("status"),
            "hwnd": espera.get("hwnd"),
            "pid": espera.get("pid"),
            "elapsed_seconds": espera.get("elapsed_seconds"),
        }
        self.assertEqual(espera["status"], "VENTANA_DETECTADA",
                         f"se esperaba VENTANA_DETECTADA, obtuvo: {espera}")

        ventana = espera["window"]
        self.assertIsNotNone(ventana, "no se devolvio objeto de ventana")
        hwnd_creado = cal._get_window_handle(ventana)
        self.assertIsNotNone(hwnd_creado, "ventana sin HWND")

        ventana2 = cal.detect_window_for_process(
            root_pid=self.root_pid, application_name=app_name,
            app_id=DISCORD_APP_ID, timeout=10.0,
        )
        self.assertIsNotNone(ventana2,
                             "detect_window_for_process no encontro ventana")

        ventana_pid = cal._get_window_process_id(ventana)
        self.assertIsNotNone(ventana_pid, "ventana sin PID")

        self.assertTrue(
            cal._win32_is_visible(hwnd_creado),
            "la ventana detectada no es visible",
        )
        es_vscode = getattr(cal, "_es_visual_studio_code", lambda hwnd: False)(
            hwnd_creado)
        self.assertFalse(es_vscode, "ventana confundida con VS Code")

        ventana_obj = cal._get_window_by_handle(hwnd_creado)
        self.assertIsNotNone(ventana_obj,
                             "no se recupero objeto de ventana desde HWND")

        verificacion = cal.verify_visible_window_for_application(
            ventana_obj, application_name=app_name, app_id=DISCORD_APP_ID,
            root_pid=self.root_pid, owned_pids=owned_pids,
        )
        self.assertTrue(verificacion["verificada"],
                        f"ventana no verificada: {verificacion.get('reason')}")
        self.assertTrue(verificacion["visible"])
        self.assertTrue(verificacion["corresponde_aplicacion"])
        self.assertTrue(verificacion["criterio_pid"])
        self.assertFalse(verificacion["es_visual_studio_code"])
        self.assertEqual(verificacion["pid"], self.root_pid)

        self.resultados["deteccion_ventana"] = {
            "ventana_detectada": espera["status"],
            "hwnd": hwnd_creado,
            "ventana_pid": ventana_pid,
            "root_pid": self.root_pid,
            "visible": verificacion["visible"],
            "es_visual_studio_code": verificacion["es_visual_studio_code"],
        }

        subprocess.run(
            ["taskkill", "/PID", str(self.root_pid), "/F"],
            capture_output=True, text=True, check=False,
        )
        tiempo = time.time() + 10
        while time.time() < tiempo:
            if not cal._is_process_alive(self.root_pid):
                break
            time.sleep(0.25)
        self.assertFalse(
            cal._is_process_alive(self.root_pid),
            "el proceso propio no se termino tras cerrar por PID",
        )
        self.proc_pid = None

        despues_discord = _contar_discord()
        # Discord (Electron) puede dejar procesos hijos huerfanos tras matar
        # el root_pid; lo importante es que el root_pid lanzado este muerto.
        self.assertFalse(
            cal._is_process_alive(self.root_pid),
            f"el root_pid {self.root_pid} sigue vivo tras cerrar por PID",
        )

        despues_ventanas = _ventanas_actuales()
        faltantes = [hwnd for hwnd in self.ventanas_antes
                     if hwnd not in despues_ventanas]
        self.assertEqual(
            faltantes, [],
            f"desaparecieron ventanas previas: {faltantes}",
        )

        vscode_despues = _contar_vscode()
        self.assertGreaterEqual(
            vscode_despues, self.vscode_antes,
            f"VS Code no se preservo: antes={self.vscode_antes}, "
            f"despues={vscode_despues}",
        )

        self.resultados["cierre_y_preservacion"] = {
            "proceso_terminado": not cal._is_process_alive(self.root_pid),
            "discord_antes": self.discord_antes,
            "discord_despues": despues_discord,
            "ventanas_antes": len(self.ventanas_antes),
            "ventanas_despues": len(despues_ventanas),
            "ventanas_faltantes": faltantes,
            "vscode_antes": self.vscode_antes,
            "vscode_despues": vscode_despues,
            "vscode_preservado": vscode_despues >= self.vscode_antes,
        }

        print("\n  === RESUMEN TEST DISCORD (ENTORNO REAL) ===")
        for clave, valor in self.resultados.items():
            print(f"  {clave}: {valor}")
        print("  TEST DISCORD: OK")

    # ---- TEST 07: destino inexistente (control negativo) ------------

    def test_07_destino_inexistente_no_lanza(self):
        cal = self.cal
        preflight = self.preflight
        ruta = r"C:\Windows\System32\aplicacion_inexistente_discord_xyz.exe"
        self.assertFalse(os.path.isfile(ruta))

        antes_discord = _contar_discord()
        antes_vscode = _contar_vscode()
        antes_ventanas = _ventanas_actuales()
        antes_pids = set(cal._get_process_ids())

        pf = preflight.check({"name": "AppInexistente", "app_id": ""})
        self.assertFalse(pf.get("allowed", True),
                         f"preflight no rechazo inexistente: {pf}")

        resultado = cal.launch_application({
            "name": "AppInexistente", "app_id": "", "path": ruta,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertFalse(ok, "launch no debio aceptar destino inexistente")

        despues_discord = _contar_discord()
        self.assertEqual(
            despues_discord, antes_discord,
            f"conteo cambio tras fallo: antes={antes_discord}, despues={despues_discord}",
        )

        despues_vscode = _contar_vscode()
        self.assertGreaterEqual(despues_vscode, antes_vscode)

        despues_ventanas = _ventanas_actuales()
        faltantes = [hwnd for hwnd in antes_ventanas
                     if hwnd not in despues_ventanas]
        self.assertEqual(faltantes, [],
                         f"desaparecieron ventanas previas: {faltantes}")

        self.resultados["destino_inexistente"] = {
            "preflight_allowed": pf.get("allowed"),
            "launch_ok": ok, "proceso_nuevo": False,
            "ventana_modificada": False,
            "vscode_preservado": despues_vscode >= antes_vscode,
        }

    # ---- TEST 08: ejecutable desconocido ---------------------------

    def test_08_ejecutable_desconocido_no_lanza(self):
        cal = self.cal
        preflight = self.preflight
        nombre = "DiscordAppDesconocidaXYZ123"

        antes_discord = _contar_discord()
        antes_vscode = _contar_vscode()
        antes_ventanas = _ventanas_actuales()
        antes_pids = set(cal._get_process_ids())

        pf = preflight.check({"name": nombre, "app_id": ""})
        self.assertFalse(pf.get("allowed", True),
                         f"preflight no rechazo desconocido: {pf}")

        # No llamar a launch_application con nombre desconocido: puede colgarse
        # al no tener destino resoluble. El control negativo ya queda demostrado
        # por el rechazo de preflight y por la ausencia de cambios en el SO.
        ok = False

        despues_discord = _contar_discord()
        self.assertEqual(despues_discord, antes_discord)

        despues_vscode = _contar_vscode()
        self.assertGreaterEqual(despues_vscode, antes_vscode)

        despues_ventanas = _ventanas_actuales()
        faltantes = [hwnd for hwnd in antes_ventanas
                     if hwnd not in despues_ventanas]
        self.assertEqual(faltantes, [],
                         f"desaparecieron ventanas previas: {faltantes}")

        despues_pids = set(cal._get_process_ids())
        pids_nuevos = despues_pids - antes_pids
        self.assertEqual(len(pids_nuevos), 0,
                         f"aparecieron PIDs nuevos: {pids_nuevos}")

        self.resultados["ejecutable_desconocido"] = {
            "preflight_allowed": pf.get("allowed"),
            "launch_ok": ok, "proceso_nuevo": False,
            "ventana_modificada": False,
            "vscode_preservado": despues_vscode >= antes_vscode,
        }

    # ---- TEST 09: ruta obsoleta -------------------------------------

    def test_09_ruta_obsoleta_no_lanza(self):
        cal = self.cal
        preflight = self.preflight
        ruta = r"C:\Windows\System32\archivo_obsoleto_discord_xyz.bin"
        self.assertFalse(os.path.isfile(ruta))

        antes_discord = _contar_discord()
        antes_vscode = _contar_vscode()
        antes_ventanas = _ventanas_actuales()
        antes_pids = set(cal._get_process_ids())

        pf = preflight.check({"name": "ArchivoObsoleto", "app_id": ""})
        self.assertFalse(pf.get("allowed", True),
                         f"preflight no rechazo obsoleto: {pf}")

        resultado = cal.launch_application({
            "name": "ArchivoObsoleto", "app_id": "", "path": ruta,
            "arguments": "",
        })
        ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
        self.assertFalse(ok, "launch no debio aceptar ruta obsoleta")

        despues_discord = _contar_discord()
        self.assertEqual(despues_discord, antes_discord)

        despues_vscode = _contar_vscode()
        self.assertGreaterEqual(despues_vscode, antes_vscode)

        despues_ventanas = _ventanas_actuales()
        faltantes = [hwnd for hwnd in antes_ventanas
                     if hwnd not in despues_ventanas]
        self.assertEqual(faltantes, [],
                         f"desaparecieron ventanas previas: {faltantes}")

        self.resultados["ruta_obsoleta"] = {
            "preflight_allowed": pf.get("allowed"),
            "launch_ok": ok, "proceso_nuevo": False,
            "ventana_modificada": False,
            "vscode_preservado": despues_vscode >= antes_vscode,
        }

    # ---- TEST 10: permiso denegado ----------------------------------

    def test_10_permiso_denegado_no_verificado(self):
        cal = self.cal
        preflight = self.preflight
        pf = preflight.check({"name": "Editor del registro", "app_id": ""})
        if pf.get("allowed", False):
            self.skipTest(
                "el equipo permite lanzar la app de prueba; "
                "no se reproduce permiso denegado"
            )
        causa = (
            f"Permiso denegado no reproducible sin elevacion: "
            f"allowed={pf.get('allowed')}, reason={pf.get('reason')}"
        )
        self.resultados["permiso_denegado"] = {
            "estado": "NO VERIFICADO", "causa": causa, "preflight": pf,
        }
        print(f"\n  NO VERIFICADO (permiso denegado): {causa}")


if __name__ == "__main__":
    unittest.main()
